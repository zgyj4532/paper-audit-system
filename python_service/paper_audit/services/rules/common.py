from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

DEFAULT_FOCUS_AREAS = ("typo", "format", "logic", "reference")

_CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_CODE_COMMENT_PREFIXES = ("///", "#")
_CODE_LINE_PATTERN = re.compile(
    r"^(?:\s*(?:```|//|/\*|\*|#|///)|\s*(?:using|import|from|public|private|protected|class|def|void|int|float|double|string|bool|namespace)\b|.*[{};].*)",
    re.IGNORECASE,
)
_CODE_TOKEN_PATTERN = re.compile(
    r"\b(?:using|import|class|def|return|void|public|private|protected|namespace)\b",
    re.IGNORECASE,
)


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


def _strip_inline_code_comment(line: str) -> str:
    stripped = str(line or "").strip()
    if not stripped:
        return ""
    if any(stripped.startswith(prefix) for prefix in _CODE_COMMENT_PREFIXES):
        return ""

    for marker in _CODE_COMMENT_PREFIXES:
        marker_index = stripped.find(marker)
        if marker_index > 0:
            candidate = stripped[:marker_index].rstrip()
            if candidate and (
                _CODE_LINE_PATTERN.search(candidate)
                or _CODE_TOKEN_PATTERN.search(candidate)
                or re.search(r"\b[A-Za-z_][\w.]*\s*\(", candidate)
            ):
                return candidate
    return stripped


def _is_code_line(line: str) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False
    if any(stripped.startswith(prefix) for prefix in _CODE_COMMENT_PREFIXES):
        return True

    normalized = _strip_inline_code_comment(stripped)
    if not normalized:
        return False
    if _CODE_LINE_PATTERN.search(normalized):
        return True
    if "#" in normalized and not _CHINESE_CHAR_PATTERN.search(normalized):
        return True
    if _CODE_TOKEN_PATTERN.search(normalized) and not _CHINESE_CHAR_PATTERN.search(
        normalized
    ):
        return True
    if normalized.count(";") >= 1 and not _CHINESE_CHAR_PATTERN.search(normalized):
        return True
    if re.search(
        r"\b[A-Za-z_][\w.]*\s*\(", normalized
    ) and not _CHINESE_CHAR_PATTERN.search(normalized):
        return True
    return False


def is_code_like_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    if "```" in stripped:
        return True

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return False

    if len(lines) == 1 and any(
        lines[0].startswith(prefix) for prefix in _CODE_COMMENT_PREFIXES
    ):
        return True

    normalized_lines = [_strip_inline_code_comment(line) for line in lines]
    code_line_count = sum(1 for line in lines if _is_code_line(line))
    if len(lines) == 1:
        return code_line_count == 1 and not _CHINESE_CHAR_PATTERN.search(
            normalized_lines[0] or lines[0]
        )

    if code_line_count >= 2 and code_line_count / len(lines) >= 0.6:
        return True

    if code_line_count == len(lines) and not _CHINESE_CHAR_PATTERN.search(
        "\n".join(normalized_lines)
    ):
        return True

    return False


def is_code_like_section(section: Dict[str, Any]) -> bool:
    if not isinstance(section, dict):
        return False
    format_info = get_section_format(section)
    font_name = str(format_info.get("font") or "").lower()
    if any(
        marker in font_name
        for marker in (
            "consolas",
            "courier",
            "monaco",
            "fira code",
            "lucida console",
        )
    ):
        return True
    return is_code_like_text(get_section_text(section))
