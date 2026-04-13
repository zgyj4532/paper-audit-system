from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

DEFAULT_FOCUS_AREAS = ("typo", "format", "logic", "reference")


@dataclass(slots=True)
class RuleIssue:
    issue_type: str
    severity: int
    message: str
    suggestion: str | None = None
    position: Dict[str, Any] | None = None
    original: str | None = None
    rule_id: str | None = None

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "issue_type": self.issue_type,
            "severity": max(1, min(int(self.severity), 5)),
            "message": self.message,
        }
        if self.suggestion:
            payload["suggestion"] = self.suggestion
        if self.position:
            payload["position"] = self.position
        if self.original:
            payload["original"] = self.original
        if self.rule_id:
            payload["rule_id"] = self.rule_id
        return payload


def normalize_focus_areas(focus_areas: Iterable[str] | None) -> set[str]:
    return {
        str(area).strip()
        for area in (focus_areas or DEFAULT_FOCUS_AREAS)
        if str(area).strip()
    }


def make_position(text: str | None, needle: str | None) -> Dict[str, int]:
    if not text or not needle:
        return {"start_char": 0, "end_char": 0}
    start = text.find(needle)
    if start < 0:
        return {"start_char": 0, "end_char": min(len(text), len(needle))}
    return {"start_char": start, "end_char": start + len(needle)}


def add_issue(
    issues: List[Dict[str, Any]],
    *,
    issue_type: str,
    severity: int,
    message: str,
    suggestion: str | None = None,
    text: str | None = None,
    needle: str | None = None,
    rule_id: str | None = None,
) -> None:
    issues.append(
        RuleIssue(
            issue_type=issue_type,
            severity=severity,
            message=message,
            suggestion=suggestion,
            position=make_position(text, needle) if text and needle else None,
            original=needle,
            rule_id=rule_id,
        ).as_dict()
    )


def split_lines(text: str) -> List[str]:
    return [line for line in (part.strip() for part in text.splitlines()) if line]


def get_sections(parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
    return [section for section in sections if isinstance(section, dict)]


def get_section_text(section: Dict[str, Any]) -> str:
    return str(section.get("raw_text") or section.get("text") or "")


def get_section_format(section: Dict[str, Any]) -> Dict[str, Any]:
    formatting = section.get("formatting")
    return formatting if isinstance(formatting, dict) else {}


def extract_text_from_parsed_data(parsed_data: Dict[str, Any]) -> str:
    text_parts: List[str] = []
    for section in get_sections(parsed_data):
        raw_text = get_section_text(section)
        if raw_text:
            text_parts.append(raw_text)
    return "\n".join(text_parts)
