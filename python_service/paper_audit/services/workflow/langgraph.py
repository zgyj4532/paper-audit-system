from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, TypedDict

from ...config import settings
from ..llm import build_qwen_client, normalize_focus_areas
from ..rules import check_consistency_rules, check_text_rules, detect_reference_entries
from ..vector import (
    can_use_local_reference_verifier,
    query_papers,
    resolve_reference_verifier_backend,
    verify_reference_locally,
)


class AuditState(TypedDict, total=False):
    parsed_data: Dict[str, Any]
    chunks: List[Dict[str, Any]]
    chunk_reviews: List[Dict[str, Any]]
    reference_verification: List[Dict[str, Any]]
    consistency_issues: List[Dict[str, Any]]
    summary: Dict[str, Any]
    backend: str


def split_into_chunks(
    parsed_data: Dict[str, Any], chunk_size: int = 800, overlap: int = 100
) -> List[Dict[str, Any]]:
    sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
    chunks: List[Dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        text = str(section.get("raw_text") or section.get("text") or "")
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append({"section_id": section.get("id"), "text": text[start:end]})
            if end == len(text):
                break
            start = end - overlap if end - overlap > start else end
    return chunks


def _fast_local_only() -> bool:
    return os.environ.get("PAPER_AUDIT_FAST_LOCAL_ONLY", "0").strip() == "1"


def _issue_span(issue: Dict[str, Any]) -> tuple[int | None, int | None]:
    position = issue.get("position") if isinstance(issue, dict) else None
    if isinstance(position, dict):
        start = position.get("start_char")
        end = position.get("end_char")
        if isinstance(start, int) and isinstance(end, int):
            return start, end
    return None, None


def _is_same_issue(
    left: Dict[str, Any], right: Dict[str, Any], tolerance: int = 3
) -> bool:
    if left.get("issue_type") != right.get("issue_type"):
        return False
    if str(left.get("original", "")).strip() != str(right.get("original", "")).strip():
        return False

    left_start, left_end = _issue_span(left)
    right_start, right_end = _issue_span(right)
    if left_start is None or right_start is None:
        return True

    return (
        abs(left_start - right_start) <= tolerance
        and abs(left_end - right_end) <= tolerance
    )


def _dedupe_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if any(_is_same_issue(existing, issue) for existing in deduped):
            continue
        deduped.append(issue)
    return deduped


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


def _normalize_issue_position(
    issue: Dict[str, Any], text: str
) -> Dict[str, Any]:
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
            normalized["position"] = {
                "start_char": start_char,
                "end_char": end_char,
            }
        else:
            current_width = max(0, model_end - model_start)
            original_width = len(original)
            if current_width < original_width or text[model_start:model_end] != original:
                normalized["position"] = {
                    "start_char": start_char,
                    "end_char": end_char,
                }

    return normalized


def _normalize_issue_positions(
    issues: List[Dict[str, Any]], text: str
) -> List[Dict[str, Any]]:
    return [_normalize_issue_position(issue, text) for issue in issues]


def _batch_items(items: List[Any], batch_size: int) -> List[List[Any]]:
    size = max(1, batch_size)
    return [items[index : index + size] for index in range(0, len(items), size)]


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
        return [
            {
                "issue_type": "review_error",
                "severity": 1,
                "message": str(exc),
                "suggestion": "retry later",
            }
        ]


async def _verify_reference_with_qwen(
    client: Any, reference: Dict[str, Any]
) -> Dict[str, Any]:
    text = reference.get("text") or reference.get("raw_text") or str(reference)
    retrieved = query_papers(text, n_results=3) if text else []
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


async def verify_references(references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    backend = resolve_reference_verifier_backend()

    if _fast_local_only() or backend == "local":
        for reference in references:
            local_result = _verify_reference_with_local(reference)
            if _fast_local_only():
                local_result["reason"] = "fast_local_only"
                local_result["risk_flags"] = list(
                    dict.fromkeys(
                        ["fast_local_only", *local_result.get("risk_flags", [])]
                    )
                )
            results.append(local_result)
        return results

    client = build_qwen_client()
    batch_size = max(1, int(getattr(settings, "LLM_QWEN_BATCH_SIZE", 4)))

    for batch in _batch_items(list(references), batch_size):
        batch_results = await asyncio.gather(
            *[_verify_reference_with_qwen(client, reference) for reference in batch]
        )
        if can_use_local_reference_verifier():
            for index, item in enumerate(batch_results):
                if not isinstance(item, dict):
                    continue
                risk_flags = set(item.get("risk_flags", []))
                if "llm_error" in risk_flags or (
                    backend == "auto" and item.get("verdict") == "unverified"
                ):
                    batch_results[index] = _verify_reference_with_local(batch[index])
        results.extend(batch_results)

    return results


async def review_document(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    focus_areas = normalize_focus_areas(None)
    chunks = split_into_chunks(parsed_data)
    chunk_reviews: List[Dict[str, Any]] = []
    fast_local_only = _fast_local_only()

    client = build_qwen_client() if not fast_local_only else None
    batch_size = max(1, int(getattr(settings, "LLM_QWEN_BATCH_SIZE", 4)))

    for batch in _batch_items(chunks, batch_size):
        local_issue_sets = [
            check_text_rules(chunk["text"], focus_areas) for chunk in batch
        ]
        if fast_local_only or client is None:
            llm_issue_sets = [[] for _ in batch]
        else:
            llm_issue_sets = await asyncio.gather(
                *[
                    _review_chunk_with_qwen(client, chunk, focus_areas)
                    for chunk in batch
                ]
            )

        for chunk, local_issues, llm_issues in zip(
            batch, local_issue_sets, llm_issue_sets
        ):
            normalized_local_issues = _normalize_issue_positions(
                [issue for issue in local_issues if isinstance(issue, dict)],
                chunk["text"],
            )
            normalized_llm_issues = _normalize_issue_positions(
                [issue for issue in llm_issues if isinstance(issue, dict)],
                chunk["text"],
            )
            merged_issues = _dedupe_issues(
                normalized_local_issues + normalized_llm_issues
            )
            chunk_reviews.append(
                {
                    "section_id": chunk.get("section_id"),
                    "text": chunk.get("text"),
                    "local_issues": normalized_local_issues,
                    "llm_issues": normalized_llm_issues,
                    "issues": merged_issues,
                    "issue_count": len(merged_issues),
                }
            )

    references = detect_reference_entries(parsed_data)
    reference_verification = await verify_references(references)
    consistency_issues = check_consistency_rules(parsed_data)

    return {
        "backend": "qwen",
        "chunks": chunks,
        "chunk_reviews": chunk_reviews,
        "reference_verification": reference_verification,
        "consistency_issues": consistency_issues,
        "summary": {
            "chunk_count": len(chunks),
            "reference_count": len(references),
            "chunk_issue_count": sum(
                item.get("issue_count", 0) for item in chunk_reviews
            ),
            "consistency_issue_count": len(consistency_issues),
            "qwen_batch_size": batch_size,
        },
    }


def build_workflow():
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return None

    graph = StateGraph(AuditState)

    async def splitter_node(state: AuditState) -> Dict[str, Any]:
        parsed_data = state.get("parsed_data", {})
        return {"chunks": split_into_chunks(parsed_data)}

    async def review_node(state: AuditState) -> Dict[str, Any]:
        parsed_data = state.get("parsed_data", {})
        return await review_document(parsed_data)

    graph.add_node("splitter", splitter_node)
    graph.add_node("review", review_node)
    graph.set_entry_point("splitter")
    graph.add_edge("splitter", "review")
    graph.add_edge("review", END)

    return graph.compile()
