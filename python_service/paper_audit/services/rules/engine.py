from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List

import httpx

from ...config import settings
from .common import DEFAULT_FOCUS_AREAS, extract_text_from_parsed_data
from .consistency import check_consistency_rules
from .document import check_document_rules
from .references import check_reference_content_rules, detect_reference_entries
from .table import check_table_rules
from .text import check_text_rules

logger = logging.getLogger(__name__)

JAVA_AUDIT_PATH = "/api/v1/rules/audit"
JAVA_HEALTH_PATH = "/api/v1/rules/health"
_SEVERITY_TO_SCORE = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
}

__all__ = [
    "DEFAULT_FOCUS_AREAS",
    "JAVA_AUDIT_PATH",
    "JAVA_HEALTH_PATH",
    "audit_document_via_java_http",
    "check_consistency_rules",
    "check_document_rules",
    "check_reference_content_rules",
    "check_table_rules",
    "check_text_rules",
    "build_java_audit_request",
    "detect_reference_entries",
    "extract_text_from_parsed_data",
    "normalize_java_audit_response",
]


def _unwrap_parsed_data(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(parsed_data, dict):
        return {}
    if any(key in parsed_data for key in ("sections", "references", "metadata")):
        return parsed_data
    nested = parsed_data.get("data")
    if isinstance(nested, dict):
        return nested
    return parsed_data


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return str(value)


def _build_java_props(section: Dict[str, Any]) -> Dict[str, str]:
    props: Dict[str, str] = {}

    formatting = section.get("formatting")
    if isinstance(formatting, dict):
        for key, value in formatting.items():
            props[f"formatting.{key}"] = _stringify(value)

    coordinates = section.get("coordinates")
    if isinstance(coordinates, dict):
        for key, value in coordinates.items():
            props[f"coordinates.{key}"] = _stringify(value)

    position = section.get("position")
    if isinstance(position, dict):
        for key, value in position.items():
            props[f"position.{key}"] = _stringify(value)

    xml_path = section.get("xml_path")
    if xml_path is not None:
        props["xml_path"] = _stringify(xml_path)

    if section.get("is_table") is not None:
        props["is_table"] = _stringify(section.get("is_table"))

    element_type = section.get("element_type") or section.get("type")
    if element_type is not None:
        props["element_type"] = _stringify(element_type)

    return props


def build_java_audit_request(
    parsed_data: Dict[str, Any],
    *,
    source_file: str | None = None,
    target_rule_set: str | None = None,
) -> Dict[str, Any]:
    data = _unwrap_parsed_data(parsed_data)
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    sections = data.get("sections", []) if isinstance(data, dict) else []
    references = data.get("references", []) if isinstance(data, dict) else []
    if not references:
        references = detect_reference_entries(data)

    request_metadata: Dict[str, Any] = {}
    if isinstance(metadata, dict):
        title = metadata.get("title") or data.get("title")
        if title is None and source_file:
            title = Path(source_file).stem
        if title is not None:
            request_metadata["title"] = title

        total_pages = metadata.get("total_pages") or metadata.get("page_count")
        if total_pages is not None:
            request_metadata["pageCount"] = total_pages

        margin_top = metadata.get("margin_top") or metadata.get("marginTop")
        if margin_top is not None:
            request_metadata["marginTop"] = margin_top

        margin_bottom = metadata.get("margin_bottom") or metadata.get("marginBottom")
        if margin_bottom is not None:
            request_metadata["marginBottom"] = margin_bottom

    request_sections: List[Dict[str, Any]] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            request_sections.append(
                {
                    "sectionId": section.get("section_id") or section.get("id"),
                    "type": section.get("element_type") or section.get("type"),
                    "level": section.get("level"),
                    "text": section.get("raw_text") or section.get("text") or "",
                    "props": _build_java_props(section),
                }
            )

    request_references: List[Dict[str, Any]] = []
    if isinstance(references, list):
        for index, reference in enumerate(references, start=1):
            if not isinstance(reference, dict):
                continue
            raw_text = reference.get("raw_text") or reference.get("text") or ""
            request_references.append(
                {
                    "refId": reference.get("ref_id")
                    or reference.get("id")
                    or reference.get("index")
                    or index,
                    "rawText": raw_text,
                    "isValidFormat": reference.get("is_valid_format"),
                }
            )

    doc_id = data.get("doc_id") or data.get("docId") or data.get("id")
    if doc_id is None and source_file:
        doc_id = Path(source_file).stem

    return {
        "docId": doc_id or "",
        "targetRuleSet": target_rule_set or settings.DEFAULT_ENABLED_MODULES,
        "metadata": request_metadata,
        "sections": request_sections,
        "references": request_references,
    }


async def audit_document_via_java_http(
    parsed_data: Dict[str, Any],
    *,
    source_file: str | None = None,
    target_rule_set: str | None = None,
    timeout_seconds: int | None = None,
) -> Dict[str, Any]:
    base_url = str(settings.ENGINE_JAVA_BASE_URL).rstrip("/")
    timeout = float(timeout_seconds or settings.ENGINE_JAVA_TIMEOUT_SECONDS)
    request_payload = build_java_audit_request(
        parsed_data,
        source_file=source_file,
        target_rule_set=target_rule_set,
    )

    logger.info(
        "Calling Java audit API: base_url=%s, docId=%s, sections=%s, references=%s",
        base_url,
        request_payload.get("docId"),
        len(request_payload.get("sections", [])),
        len(request_payload.get("references", [])),
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        response = await client.post(JAVA_AUDIT_PATH, json=request_payload)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Java audit response must be a JSON object")
        logger.info(
            "Java audit API completed: status_code=%s, issue_count=%s",
            response.status_code,
            len(payload.get("issues", [])) if isinstance(payload.get("issues"), list) else 0,
        )
        return payload


def _normalize_java_issue_severity(severity: Any) -> int:
    severity_name = _stringify(severity).upper()
    if severity_name in _SEVERITY_TO_SCORE:
        return _SEVERITY_TO_SCORE[severity_name]
    return 1


def _infer_issue_type_from_code(code: str) -> str:
    upper_code = code.upper()
    if upper_code.startswith(("FORMAT", "THESIS")):
        return "format"
    if upper_code.startswith(("REF", "REFERENCE")):
        return "reference"
    if upper_code.startswith(("CONSIST", "STYLE", "LOGIC", "INTEGRITY")):
        return "logic"
    return "rule"


def normalize_java_audit_response(
    response: Dict[str, Any],
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    raw_issues = response.get("issues", []) if isinstance(response, dict) else []
    if isinstance(raw_issues, list):
        for issue in raw_issues:
            if not isinstance(issue, dict):
                continue
            code = _stringify(issue.get("code") or issue.get("rule_code") or "")
            section_id = issue.get("sectionId") or issue.get("section_id")
            normalized_issue = {
                "issue_type": _infer_issue_type_from_code(code),
                "severity": _normalize_java_issue_severity(issue.get("severity")),
                "message": _stringify(issue.get("message")),
                "suggestion": _stringify(issue.get("suggestion")),
                "original": _stringify(
                    issue.get("originalSnippet") or issue.get("original_snippet")
                ),
                "rule_id": code,
                "position": {"section_id": section_id} if section_id is not None else {},
                "source": "java_http",
                "java_issue": issue,
            }
            issues.append(normalized_issue)

    summary = response.get("summary", {}) if isinstance(response, dict) else {}
    score_impact = response.get("score_impact", 0) if isinstance(response, dict) else 0
    return {
        "backend": "java_http",
        "issues": issues,
        "issue_count": len(issues),
        "score_impact": score_impact,
        "summary": summary if isinstance(summary, dict) else {},
        "raw": response,
    }
