from __future__ import annotations

from typing import Any, Dict, List

from ..rules.references import detect_reference_entries
from .shared import split_into_chunks, section_key


def _build_java_section_reviews(
    parsed_data: Dict[str, Any], issues: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
    issues_by_section: Dict[str, List[Dict[str, Any]]] = {}
    unassigned_issues: List[Dict[str, Any]] = []

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        position = issue.get("position") if isinstance(issue.get("position"), dict) else {}
        section_id = issue.get("section_id")
        if section_id is None and isinstance(position, dict):
            section_id = position.get("section_id")
        key = section_key(section_id)
        if key:
            issues_by_section.setdefault(key, []).append(issue)
        else:
            unassigned_issues.append(issue)

    section_reviews: List[Dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue
        section_id = section.get("id") or section.get("section_id") or index
        key = section_key(section_id)
        section_issues = issues_by_section.pop(key, [])
        section_reviews.append(
            {
                "section_id": section_id,
                "kind": "table" if bool(section.get("is_table")) else "section",
                "text": section.get("raw_text") or section.get("text"),
                "is_table": bool(section.get("is_table")),
                "issues": section_issues,
                "issue_count": len(section_issues),
                "backend": "java_http",
                "java_issues": section_issues,
            }
        )

    for key, section_issues in issues_by_section.items():
        section_reviews.append(
            {
                "section_id": key,
                "kind": "document",
                "text": "",
                "is_table": False,
                "issues": section_issues,
                "issue_count": len(section_issues),
                "backend": "java_http",
                "java_issues": section_issues,
            }
        )

    if unassigned_issues:
        section_reviews.append(
            {
                "section_id": None,
                "kind": "document",
                "text": "",
                "is_table": False,
                "issues": unassigned_issues,
                "issue_count": len(unassigned_issues),
                "backend": "java_http",
                "java_issues": unassigned_issues,
            }
        )

    return section_reviews


async def review_document_java_http(
    parsed_data: Dict[str, Any],
    source_file: str | None = None,
    *,
    audit_java: Any,
    normalize_java_response: Any,
    split_chunks=split_into_chunks,
    detect_refs=detect_reference_entries,
) -> Dict[str, Any]:
    chunks = split_chunks(parsed_data)
    java_response = await audit_java(parsed_data, source_file=source_file)
    normalized_java = normalize_java_response(java_response)
    section_reviews = _build_java_section_reviews(parsed_data, normalized_java["issues"])

    return {
        "backend": "java_http",
        "java_review": normalized_java["raw"],
        "chunks": chunks,
        "chunk_reviews": section_reviews,
        "section_reviews": section_reviews,
        "reference_verification": [],
        "consistency_issues": [],
        "summary": {
            "chunk_count": len(chunks),
            "section_count": len(section_reviews),
            "reference_count": len(detect_refs(parsed_data)),
            "chunk_issue_count": len(normalized_java["issues"]),
            "consistency_issue_count": 0,
            "java_issue_count": len(normalized_java["issues"]),
            "java_score_impact": normalized_java.get("score_impact", 0),
        },
    }
