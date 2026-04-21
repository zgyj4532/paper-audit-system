from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List

from ...config import settings
from ..llm import build_qwen_client, normalize_focus_areas
from ..rules import check_consistency_rules, check_table_rules, check_text_rules
from ..rules.references import detect_reference_entries
from ..vector import (
    can_use_local_reference_verifier,
    query_papers,
    resolve_reference_verifier_backend,
    verify_reference_locally,
)
from .shared import (
    dedupe_issues,
    fast_local_only,
    split_into_chunks,
)

logger = logging.getLogger(__name__)


def _skipped_chunk_review(chunk: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "section_id": chunk.get("section_id"),
        "kind": chunk.get("kind", "text"),
        "text": chunk.get("text"),
        "is_table": bool(chunk.get("is_table")),
        "is_code_block": True,
        "review_skipped": reason,
        "local_issues": [],
        "llm_issues": [],
        "issues": [],
        "issue_count": 0,
    }


def _group_chunks_by_section_id(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    index_by_key: Dict[Any, int] = {}

    for chunk in chunks:
        key = chunk.get("section_id")
        group_index = index_by_key.get(key)
        if group_index is None:
            group_index = len(groups)
            index_by_key[key] = group_index
            groups.append({"section_id": chunk.get("section_id"), "chunks": []})
        groups[group_index]["chunks"].append(chunk)

    return groups


def _find_best_original_span(
    text: str, original: str, model_start: int | None = None
) -> tuple[int, int] | None:
    if not text or not original:
        return None

    matches: List[tuple[int, int]] = []
    cursor = 0
    while True:
        index = text.find(original, cursor)
        if index < 0:
            break
        matches.append((index, index + len(original)))
        cursor = index + 1

    if not matches:
        return None

    if model_start is None:
        return matches[0]

    return min(matches, key=lambda span: abs(span[0] - model_start))


def _normalize_issue_position(issue: Dict[str, Any], text: str) -> Dict[str, Any]:
    if not isinstance(issue, dict):
        return issue

    normalized = dict(issue)
    original = str(normalized.get("original") or "")
    position = normalized.get("position")
    model_start: int | None = None
    model_end: int | None = None
    if isinstance(position, dict):
        start = position.get("start_char")
        end = position.get("end_char")
        if isinstance(start, int) and isinstance(end, int):
            model_start = start
            model_end = end

    best_span = _find_best_original_span(text, original, model_start)
    if best_span is not None:
        start_char, end_char = best_span
        if model_start is None or model_end is None:
            normalized["position"] = {"start_char": start_char, "end_char": end_char}
        else:
            current_width = max(0, model_end - model_start)
            original_width = len(original)
            if current_width < original_width or text[model_start:model_end] != original:
                normalized["position"] = {"start_char": start_char, "end_char": end_char}

    return normalized


def _normalize_issue_positions(
    issues: List[Dict[str, Any]], text: str
) -> List[Dict[str, Any]]:
    return [_normalize_issue_position(issue, text) for issue in issues]


async def _review_chunk_with_qwen(
    client: Any, chunk: Dict[str, Any], focus_areas: List[str]
) -> List[Dict[str, Any]]:
    try:
        qwen_result = await client.review_chunk(
            chunk["text"],
            section_id=chunk.get("section_id"),
            strictness=3,
            focus_areas=focus_areas,
        )
        issues = qwen_result.get("issues", []) if isinstance(qwen_result, dict) else []
        return [issue for issue in issues if isinstance(issue, dict)]
    except Exception as exc:
        logger.warning(
            "Qwen chunk review failed for section %s: %s",
            chunk.get("section_id"),
            exc,
        )
        return []


async def _review_table_with_qwen(
    client: Any, table_rows: List[Dict[str, Any]], focus_areas: List[str]
) -> Dict[str, Any]:
    try:
        qwen_result = await client.review_table(
            table_rows,
            section_id=table_rows[0].get("section_id") if table_rows else None,
            strictness=3,
            doc_type="学位论文",
            degree_level="学士",
            institution="中国计量大学",
        )
        table_issues = (
            qwen_result.get("table_issues", []) if isinstance(qwen_result, dict) else []
        )
        return {
            "table_issues": [issue for issue in table_issues if isinstance(issue, dict)],
            "field_summary": (
                qwen_result.get("field_summary", {}) if isinstance(qwen_result, dict) else {}
            ),
            "critical_gaps": (
                qwen_result.get("critical_gaps", []) if isinstance(qwen_result, dict) else []
            ),
            "backend": (
                qwen_result.get("backend", "qwen") if isinstance(qwen_result, dict) else "qwen"
            ),
            "raw": qwen_result.get("raw", {}) if isinstance(qwen_result, dict) else {},
        }
    except Exception as exc:
        logger.warning(
            "Qwen table review failed for section %s: %s",
            table_rows[0].get("section_id") if table_rows else None,
            exc,
        )
        return {
            "table_issues": [],
            "field_summary": {},
            "critical_gaps": [],
            "backend": "qwen",
            "raw": {},
        }


async def _review_section_group_worker(
    client: Any,
    group: Dict[str, Any],
    focus_areas: List[str],
    fast_only: bool,
    check_text: Callable[[str, List[str]], List[Dict[str, Any]]] = check_text_rules,
    check_table: Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]] = check_table_rules,
) -> Dict[str, Any]:
    chunks = group.get("chunks", [])
    if chunks and all(bool(chunk.get("is_code_block")) for chunk in chunks):
        return _skipped_chunk_review(chunks[0], "code_block")

    if chunks and all(bool(chunk.get("is_table")) for chunk in chunks):
        table_rows = [
            {
                "section_id": row.get("section_id"),
                "table_index": row.get("table_index"),
                "row_index": row.get("row_index"),
                "cell_count": row.get("cell_count"),
                "cells": row.get("cells", []),
                "text": row.get("text"),
            }
            for row in chunks
        ]
        row_reviews = [
            {
                "section_id": row.get("section_id"),
                "kind": "row",
                "table_index": row.get("table_index"),
                "row_index": row.get("row_index"),
                "cell_count": row.get("cell_count"),
                "cells": row.get("cells", []),
                "text": row.get("text"),
                "is_table": True,
                "issues": [],
                "issue_count": 0,
            }
            for row in table_rows
        ]
        local_table_issues = check_table(table_rows, focus_areas)
        if fast_only:
            llm_table_issues: List[Dict[str, Any]] = []
            table_backend = "local"
            field_summary: Dict[str, Any] = {}
            critical_gaps: List[str] = []
        else:
            table_result = await _review_table_with_qwen(client, table_rows, focus_areas)
            llm_table_issues = table_result.get("table_issues", [])
            table_backend = table_result.get("backend", "qwen")
            field_summary = table_result.get("field_summary", {})
            critical_gaps = table_result.get("critical_gaps", [])

        normalized_local_issues = dedupe_issues(local_table_issues)
        normalized_llm_issues = dedupe_issues(llm_table_issues)
        merged_issues = dedupe_issues(normalized_local_issues + normalized_llm_issues)
        return {
            "section_id": group.get("section_id"),
            "kind": "table",
            "text": "\n".join(str(row.get("text") or "") for row in chunks if row),
            "is_table": True,
            "table_index": chunks[0].get("table_index") if chunks else None,
            "table_rows": table_rows,
            "table_issues": merged_issues,
            "local_issues": normalized_local_issues,
            "llm_issues": normalized_llm_issues,
            "issues": merged_issues,
            "issue_count": len(merged_issues),
            "row_reviews": row_reviews,
            "field_summary": field_summary,
            "critical_gaps": critical_gaps,
            "backend": table_backend,
        }

    chunk_reviews: List[Dict[str, Any]] = []
    aggregated_local_issues: List[Dict[str, Any]] = []
    aggregated_llm_issues: List[Dict[str, Any]] = []
    aggregated_issues: List[Dict[str, Any]] = []
    backend = "local" if fast_only else "qwen"

    for chunk in chunks:
        if bool(chunk.get("is_code_block")):
            review = _skipped_chunk_review(chunk, "code_block")
            chunk_reviews.append(review)
            continue

        local_issues = check_text(chunk["text"], focus_areas)
        if fast_only:
            llm_issues = []
            text_backend = "local"
        else:
            text_result = await _review_chunk_with_qwen(client, chunk, focus_areas)
            llm_issues = text_result
            text_backend = "qwen"

        normalized_local_issues = _normalize_issue_positions(
            [issue for issue in local_issues if isinstance(issue, dict)],
            chunk["text"],
        )
        normalized_llm_issues = _normalize_issue_positions(
            [issue for issue in llm_issues if isinstance(issue, dict)],
            chunk["text"],
        )
        normalized_local_issues = dedupe_issues(normalized_local_issues)
        normalized_llm_issues = dedupe_issues(normalized_llm_issues)
        merged_issues = dedupe_issues(normalized_local_issues + normalized_llm_issues)
        review = {
            "section_id": chunk.get("section_id"),
            "kind": chunk.get("kind", "text"),
            "text": chunk.get("text"),
            "is_table": False,
            "local_issues": normalized_local_issues,
            "llm_issues": normalized_llm_issues,
            "issues": merged_issues,
            "issue_count": len(merged_issues),
            "backend": text_backend,
        }

        chunk_reviews.append(review)
        backend = review.get("backend", backend)
        aggregated_local_issues.extend(review.get("local_issues", []))
        aggregated_llm_issues.extend(review.get("llm_issues", []))
        aggregated_issues.extend(review.get("issues", []))

    merged_local_issues = dedupe_issues(aggregated_local_issues)
    merged_llm_issues = dedupe_issues(aggregated_llm_issues)
    merged_issues = dedupe_issues(aggregated_issues)

    return {
        "section_id": group.get("section_id"),
        "kind": "table" if chunks and all(bool(chunk.get("is_table")) for chunk in chunks) else "section",
        "text": "\n".join(str(chunk.get("text") or "") for chunk in chunks if chunk),
        "is_table": bool(chunks) and all(bool(chunk.get("is_table")) for chunk in chunks),
        "chunks": chunks,
        "chunk_reviews": chunk_reviews,
        "local_issues": merged_local_issues,
        "llm_issues": merged_llm_issues,
        "issues": merged_issues,
        "issue_count": len(merged_issues),
        "backend": backend,
    }


async def _verify_reference_with_qwen(
    client: Any,
    reference: Dict[str, Any],
    query_papers_fn: Callable[[str, int], List[Dict[str, Any]]] = query_papers,
) -> Dict[str, Any]:
    text = reference.get("text") or reference.get("raw_text") or str(reference)
    retrieved = query_papers_fn(text, n_results=3) if text else []
    try:
        qwen_result = await client.verify_reference(
            text, retrieved, backend_hint="qwen"
        )
        return {
            "reference": reference,
            "retrieved": retrieved,
            "verdict": qwen_result.get("verdict", "unverified"),
            "confidence": qwen_result.get("confidence", "low"),
            "reason": qwen_result.get("reason", ""),
            "risk_flags": qwen_result.get("risk_flags", []),
            "llm_backend": qwen_result.get("llm_backend", "qwen"),
        }
    except Exception as exc:
        return {
            "reference": reference,
            "retrieved": retrieved,
            "verdict": "unverified",
            "confidence": "low",
            "reason": f"llm_error: {exc}",
            "risk_flags": ["llm_error"],
            "llm_backend": "qwen",
        }


def _verify_reference_with_local(reference: Dict[str, Any]) -> Dict[str, Any]:
    text = reference.get("text") or reference.get("raw_text") or str(reference)
    retrieved = query_papers(text, n_results=3) if text else []
    try:
        result = verify_reference_locally(text, retrieved)
        result["reference"] = reference
        return result
    except Exception as exc:
        return {
            "reference": reference,
            "retrieved": retrieved,
            "verdict": "unverified",
            "confidence": "low",
            "reason": f"local_error: {exc}",
            "risk_flags": ["local_error"],
            "llm_backend": "local",
            "backend": "local",
        }


async def verify_references(
    references: List[Dict[str, Any]],
    *,
    build_client: Callable[[], Any] = build_qwen_client,
    resolve_backend: Callable[[], str] = resolve_reference_verifier_backend,
    can_use_local: Callable[[], bool] = can_use_local_reference_verifier,
    query_papers_fn: Callable[[str, int], List[Dict[str, Any]]] = query_papers,
    verify_local: Callable[[str, List[Dict[str, Any]]], Dict[str, Any]] = verify_reference_locally,
    worker_batch_size: int | None = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    backend = resolve_backend()

    if fast_local_only() or backend == "local":
        for reference in references:
            local_result = _verify_reference_with_local(reference)
            if fast_local_only():
                local_result["reason"] = "fast_local_only"
                local_result["risk_flags"] = list(
                    dict.fromkeys(["fast_local_only", *local_result.get("risk_flags", [])])
                )
            results.append(local_result)
        return results

    client = build_client()
    worker_count = max(1, int(worker_batch_size or getattr(settings, "LLM_QWEN_BATCH_SIZE", 4)))
    semaphore = asyncio.Semaphore(worker_count)

    async def run_one(reference: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            if backend == "local":
                return _verify_reference_with_local(reference)
            qwen_result = await _verify_reference_with_qwen(
                client, reference, query_papers_fn=query_papers_fn
            )
            if can_use_local():
                risk_flags = set(qwen_result.get("risk_flags", []))
                if "llm_error" in risk_flags or (backend == "auto" and qwen_result.get("verdict") == "unverified"):
                    return _verify_reference_with_local(reference)
            return qwen_result

    results = await asyncio.gather(*[run_one(reference) for reference in references])
    return results


async def review_document_local(
    parsed_data: Dict[str, Any],
    source_file: str | None = None,
    *,
    build_client: Callable[[], Any] = build_qwen_client,
    normalize_areas: Callable[[Any], List[str]] = normalize_focus_areas,
    split_chunks: Callable[[Dict[str, Any]], List[Dict[str, Any]]] = split_into_chunks,
    check_text: Callable[[str, List[str]], List[Dict[str, Any]]] = check_text_rules,
    check_table: Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]] = check_table_rules,
    check_consistency: Callable[[Dict[str, Any], str | None], List[Dict[str, Any]]] = check_consistency_rules,
    detect_refs: Callable[[Dict[str, Any]], List[Dict[str, Any]]] = detect_reference_entries,
    query_papers_fn: Callable[[str, int], List[Dict[str, Any]]] = query_papers,
    resolve_backend: Callable[[], str] = resolve_reference_verifier_backend,
    verify_local: Callable[[str, List[Dict[str, Any]]], Dict[str, Any]] = verify_reference_locally,
    can_use_local: Callable[[], bool] = can_use_local_reference_verifier,
) -> Dict[str, Any]:
    focus_areas = normalize_areas(None)
    chunks = split_chunks(parsed_data)
    section_reviews: List[Dict[str, Any]] = []
    fast_only = fast_local_only()
    client: Any = None

    def ensure_client() -> Any:
        nonlocal client
        if client is None:
            client = build_client()
        return client

    worker_count = max(1, int(getattr(settings, "LLM_QWEN_BATCH_SIZE", 4)))
    semaphore = asyncio.Semaphore(worker_count)
    section_groups = _group_chunks_by_section_id(chunks)

    async def review_section_group(group: Dict[str, Any]) -> Dict[str, Any]:
        group_chunks = group.get("chunks", [])
        if group_chunks and all(bool(chunk.get("is_code_block")) for chunk in group_chunks):
            return _skipped_chunk_review(group_chunks[0], "code_block")
        async with semaphore:
            section_client = ensure_client()
            return await _review_section_group_worker(
                section_client,
                group,
                focus_areas,
                fast_only,
                check_text=check_text,
                check_table=check_table,
            )

    section_reviews = await asyncio.gather(*[review_section_group(group) for group in section_groups])

    references = detect_refs(parsed_data)
    reference_verification = await verify_references(
        references,
        build_client=build_client,
        resolve_backend=resolve_backend,
        can_use_local=can_use_local,
        query_papers_fn=query_papers_fn,
        verify_local=verify_local,
    )
    consistency_issues = check_consistency(parsed_data, source_file=source_file)

    return {
        "backend": "qwen",
        "chunks": chunks,
        "chunk_reviews": section_reviews,
        "section_reviews": section_reviews,
        "reference_verification": reference_verification,
        "consistency_issues": consistency_issues,
        "summary": {
            "chunk_count": len(chunks),
            "section_count": len(section_groups),
            "reference_count": len(references),
            "chunk_issue_count": sum(item.get("issue_count", 0) for item in section_reviews),
            "consistency_issue_count": len(consistency_issues),
            "qwen_worker_count": worker_count,
            "qwen_batch_size": worker_count,
        },
    }
