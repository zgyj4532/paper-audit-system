from __future__ import annotations

import os
from typing import Any, Dict, List

from ...config import settings
from ..rules import check_consistency_rules
from ..rules.common import is_code_like_text


def split_into_chunks(
    parsed_data: Dict[str, Any], chunk_size: int = 800, overlap: int = 100
) -> List[Dict[str, Any]]:
    sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
    chunks: List[Dict[str, Any]] = []
    table_index = 0

    def _normalize_cells(row: Any) -> List[str]:
        if not isinstance(row, list):
            return [] if row is None else [str(row)]
        return ["" if cell is None else str(cell) for cell in row]

    def _append_text_chunks(
        *,
        text: str,
        section_id: Any,
        is_table: bool,
        kind: str,
        extra: Dict[str, Any] | None = None,
    ) -> None:
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = {
                "kind": kind,
                "section_id": section_id,
                "text": text[start:end],
                "is_table": is_table,
            }
            if extra:
                chunk.update(extra)
            chunks.append(chunk)
            if end == len(text):
                break
            start = end - overlap if end - overlap > start else end

    for section in sections:
        if not isinstance(section, dict):
            continue
        is_table = bool(section.get("is_table"))
        section_id = section.get("id")

        if is_table:
            table_index += 1
            table_rows = section.get("table_rows")
            if isinstance(table_rows, list) and table_rows:
                for row_index, row in enumerate(table_rows, start=1):
                    cells = _normalize_cells(row)
                    if not cells:
                        continue
                    chunks.append(
                        {
                            "kind": "row",
                            "section_id": section_id,
                            "text": "\t".join(cells),
                            "is_table": True,
                            "table_index": table_index,
                            "row_index": row_index,
                            "cell_count": len(cells),
                            "cells": cells,
                        }
                    )
                continue

        text = str(section.get("raw_text") or section.get("text") or "")
        if not text:
            continue
        code_like = is_code_like_text(text)
        extra: Dict[str, Any] | None = None
        if is_table:
            extra = {"table_index": table_index}
        if code_like and not is_table:
            extra = {"is_code_block": True}
        _append_text_chunks(
            text=text,
            section_id=section_id,
            is_table=is_table,
            kind="table" if is_table else "text",
            extra=extra,
        )
    return chunks


def fast_local_only() -> bool:
    return os.environ.get("PAPER_AUDIT_FAST_LOCAL_ONLY", "0").strip() == "1"


def rules_backend() -> str:
    backend = str(getattr(settings, "RULE_AUDIT_BACKEND", "java_http")).strip().lower()
    return backend or "java_http"


def _issue_span(issue: Dict[str, Any]) -> tuple[int | None, int | None]:
    position = issue.get("position") if isinstance(issue, dict) else None
    if isinstance(position, dict):
        start = position.get("start_char")
        end = position.get("end_char")
        if isinstance(start, int) and isinstance(end, int):
            return start, end
    return None, None


def _freeze_issue_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(
            sorted((str(key), _freeze_issue_value(item)) for key, item in value.items())
        )
    if isinstance(value, list):
        return tuple(_freeze_issue_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_issue_value(item) for item in value))
    return value


def _issue_signature(issue: Dict[str, Any]) -> tuple[Any, ...]:
    if not isinstance(issue, dict):
        return ()
    return (
        str(issue.get("issue_type") or ""),
        str(issue.get("field_name") or ""),
        str(issue.get("original") or "").strip(),
        str(issue.get("message") or "").strip(),
        str(issue.get("suggestion") or "").strip(),
        str(issue.get("rule_id") or "").strip(),
        issue.get("severity"),
        _freeze_issue_value(issue.get("position")),
    )


def _issue_label(issue: Dict[str, Any]) -> str:
    if not isinstance(issue, dict):
        return ""
    original = issue.get("original")
    if isinstance(original, str) and original.strip():
        return original.strip()
    field_name = issue.get("field_name")
    if isinstance(field_name, str) and field_name.strip():
        return field_name.strip()
    return ""


def is_same_issue(left: Dict[str, Any], right: Dict[str, Any], tolerance: int = 3) -> bool:
    if left.get("issue_type") != right.get("issue_type"):
        return False
    if _issue_label(left) != _issue_label(right):
        return False

    left_start, left_end = _issue_span(left)
    right_start, right_end = _issue_span(right)
    if left_start is None or right_start is None:
        return True

    return (
        abs(left_start - right_start) <= tolerance
        and abs(left_end - right_end) <= tolerance
    )


def dedupe_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        signature = _issue_signature(issue)
        if signature in seen or any(is_same_issue(existing, issue) for existing in deduped):
            continue
        seen.add(signature)
        deduped.append(issue)
    return deduped


def section_key(value: Any) -> str:
    return "" if value is None else str(value)


def section_identifier(section: Dict[str, Any], fallback: int | None = None) -> Any:
    if not isinstance(section, dict):
        return fallback
    return section.get("id") or section.get("section_id") or fallback


def collect_java_blacklisted_section_ids(java_review: Dict[str, Any]) -> set[Any]:
    blacklisted: set[Any] = set()
    if not isinstance(java_review, dict):
        return blacklisted

    raw_review = java_review.get("java_review")
    if isinstance(raw_review, dict):
        for key in (
            "reviewed_section_ids",
            "reviewedSectionIds",
            "section_ids",
            "sectionIds",
        ):
            section_ids = raw_review.get(key)
            if isinstance(section_ids, list):
                for section_id in section_ids:
                    if section_id is not None:
                        blacklisted.add(section_id)

        raw_sections = raw_review.get("section_reviews") or raw_review.get("sectionReviews")
        if isinstance(raw_sections, list):
            for item in raw_sections:
                if isinstance(item, dict):
                    section_id = item.get("section_id") or item.get("sectionId")
                    if section_id is not None and item.get("issues"):
                        blacklisted.add(section_id)

        raw_issues = raw_review.get("issues")
        if isinstance(raw_issues, list):
            for issue in raw_issues:
                if not isinstance(issue, dict):
                    continue
                section_id = issue.get("sectionId") or issue.get("section_id")
                if section_id is None:
                    position = issue.get("position")
                    if isinstance(position, dict):
                        section_id = position.get("section_id")
                if section_id is not None:
                    blacklisted.add(section_id)

    section_reviews = java_review.get("section_reviews")
    if isinstance(section_reviews, list):
        for item in section_reviews:
            if not isinstance(item, dict):
                continue
            if not item.get("issues"):
                continue
            section_id = item.get("section_id")
            if section_id is not None:
                blacklisted.add(section_id)

    return blacklisted


def filter_parsed_sections(
    parsed_data: Dict[str, Any], excluded_section_ids: set[Any]
) -> Dict[str, Any]:
    if not isinstance(parsed_data, dict):
        return {}

    if not excluded_section_ids:
        return dict(parsed_data)

    filtered = dict(parsed_data)
    sections = parsed_data.get("sections", [])
    if not isinstance(sections, list):
        filtered["sections"] = []
        return filtered

    filtered_sections: List[Dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue
        section_id = section_identifier(section, index)
        if section_id in excluded_section_ids:
            continue
        filtered_sections.append(section)

    filtered["sections"] = filtered_sections
    return filtered


def merge_hybrid_reviews(
    java_review: Dict[str, Any],
    ai_review: Dict[str, Any],
    parsed_data: Dict[str, Any],
    blacklisted_section_ids: set[Any],
    source_file: str | None = None,
) -> Dict[str, Any]:
    java_section_reviews = java_review.get("section_reviews", [])
    ai_section_reviews = ai_review.get("section_reviews", [])
    combined_reviews: List[Dict[str, Any]] = []

    if isinstance(java_section_reviews, list):
        for item in java_section_reviews:
            if not isinstance(item, dict):
                continue
            section_id = item.get("section_id")
            if section_id in blacklisted_section_ids:
                combined_reviews.append(item)

    if isinstance(ai_section_reviews, list):
        for item in ai_section_reviews:
            if isinstance(item, dict):
                combined_reviews.append(item)

    combined_chunks = split_into_chunks(parsed_data)
    combined_issue_count = sum(
        item.get("issue_count", 0) for item in combined_reviews if isinstance(item, dict)
    )

    final_summary = dict(ai_review.get("summary", {}))
    final_summary.update(
        {
            "chunk_count": len(combined_chunks),
            "section_count": len(combined_reviews),
            "java_chunk_issue_count": java_review.get("summary", {}).get(
                "chunk_issue_count", 0
            ),
            "java_issue_count": java_review.get("summary", {}).get(
                "java_issue_count", 0
            ),
            "java_score_impact": java_review.get("summary", {}).get(
                "java_score_impact", 0
            ),
            "ai_chunk_issue_count": ai_review.get("summary", {}).get(
                "chunk_issue_count", 0
            ),
            "chunk_issue_count": combined_issue_count,
        }
    )

    return {
        "backend": "hybrid",
        "java_review": java_review.get("java_review", {}),
        "ai_review": ai_review,
        "chunks": combined_chunks,
        "chunk_reviews": combined_reviews,
        "section_reviews": combined_reviews,
        "java_section_reviews": java_section_reviews,
        "ai_section_reviews": ai_section_reviews,
        "reference_verification": ai_review.get("reference_verification", []),
        "consistency_issues": check_consistency_rules(parsed_data, source_file=source_file),
        "summary": final_summary,
    }
