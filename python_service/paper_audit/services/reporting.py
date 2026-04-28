from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)


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


def _issue_signature(issue: dict[str, Any]) -> tuple[Any, ...]:
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


def _dedupe_issue_list(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        signature = _issue_signature(issue)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(issue)
    return deduped


def _compact_chunk_review_for_report(chunk_review: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(chunk_review)
    issue_views: dict[str, list[dict[str, Any]]] = {}

    for key in ("local_issues", "llm_issues", "table_issues", "issues"):
        value = compacted.get(key)
        if isinstance(value, list):
            issue_views[key] = _dedupe_issue_list(
                [issue for issue in value if isinstance(issue, dict)]
            )

    if issue_views:
        merged_issues = issue_views.get("issues", [])
        if not merged_issues:
            merged_issues = _dedupe_issue_list(
                [
                    *issue_views.get("local_issues", []),
                    *issue_views.get("llm_issues", []),
                    *issue_views.get("table_issues", []),
                ]
            )
        compacted["issues"] = merged_issues
        compacted["issue_count"] = len(merged_issues)

        for key in ("local_issues", "llm_issues", "table_issues"):
            current = issue_views.get(key, [])
            if not current or current == merged_issues:
                compacted.pop(key, None)
            else:
                compacted[key] = current

    if isinstance(compacted.get("row_reviews"), list):
        compacted["row_reviews"] = [
            (
                _compact_chunk_review_for_report(row_review)
                if isinstance(row_review, dict)
                else row_review
            )
            for row_review in compacted["row_reviews"]
        ]

    return compacted


def compact_ai_review_for_report(ai_review: dict[str, Any]) -> dict[str, Any]:
    compacted = dict(ai_review)
    chunk_reviews = compacted.get("chunk_reviews")
    if isinstance(chunk_reviews, list):
        compacted["chunk_reviews"] = [
            (
                _compact_chunk_review_for_report(chunk_review)
                if isinstance(chunk_review, dict)
                else chunk_review
            )
            for chunk_review in chunk_reviews
        ]
    java_review = compacted.get("java_review")
    if isinstance(java_review, dict):
        compacted["java_review_raw"] = java_review
    return compacted


def cleanup_uploaded_source(file_path: str) -> None:
    try:
        source_path = Path(file_path).resolve()
    except Exception:
        return

    uploads_dir = settings.PYTHON_UPLOAD_DIR.resolve()
    try:
        source_path.relative_to(uploads_dir)
    except ValueError:
        return

    if not source_path.exists() or not source_path.is_file():
        return

    try:
        source_path.unlink()
    except Exception:
        logger.warning("failed to remove uploaded source file: %s", source_path)
