from __future__ import annotations

import re
from typing import Any, Dict, List

from .common import extract_text_from_parsed_data, is_code_like_section

_REFERENCE_TYPE_PATTERN = re.compile(r"\[(?P<kind>[JM])\]")
_REFERENCE_INDEX_PATTERN = re.compile(r"^\[(?P<index>\d+)\]")
_YEAR_PATTERN = re.compile(r"(?<!\d)(?P<year>\d{4})(?!\d)")
_TWO_DIGIT_YEAR_PATTERN = re.compile(r"(?<!\d)(?P<year>\d{2})(?!\d)")
_CITATION_PATTERN = re.compile(r"\[(?P<index>\d+)\]")


def detect_reference_entries(parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    references = (
        parsed_data.get("references", []) if isinstance(parsed_data, dict) else []
    )
    if references:
        return [reference for reference in references if isinstance(reference, dict)]

    text = extract_text_from_parsed_data(parsed_data)
    detected: List[Dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\[[0-9]+\]", stripped) or (
            "et al." in stripped and re.search(r"\d{4}", stripped)
        ):
            detected.append({"text": stripped})
    return detected


def _entry_text(entry: Dict[str, Any]) -> str:
    return str(entry.get("text") or entry.get("raw_text") or "").strip()


def _entry_index(entry: Dict[str, Any]) -> int | None:
    text = _entry_text(entry)
    if not text:
        return None
    match = _REFERENCE_INDEX_PATTERN.match(text)
    if match:
        return int(match.group("index"))
    index = entry.get("index")
    if isinstance(index, int):
        return index
    return None


def _count_authors(reference_text: str) -> int:
    prefix = reference_text
    separator_index = reference_text.find(".")
    if separator_index > 0:
        prefix = reference_text[:separator_index]
    prefix = prefix.split("[")[0]
    parts = [part.strip() for part in re.split(r"[，,、;；]+", prefix) if part.strip()]
    return len(parts) if parts else 1


def _extract_years(reference_text: str) -> List[int]:
    years: List[int] = []
    for match in _YEAR_PATTERN.finditer(reference_text):
        try:
            years.append(int(match.group("year")))
        except ValueError:
            continue
    return years


def _extract_two_digit_years(reference_text: str) -> List[int]:
    years: List[int] = []
    for match in _TWO_DIGIT_YEAR_PATTERN.finditer(reference_text):
        value = int(match.group("year"))
        if value < 100:
            years.append(value)
    return years


def _reference_texts(parsed_data: Dict[str, Any]) -> List[str]:
    entries = detect_reference_entries(parsed_data)
    if entries:
        return [
            _entry_text(entry)
            for entry in entries
            if _entry_text(entry) and not is_code_like_section(entry)
        ]

    text = extract_text_from_parsed_data(parsed_data)
    return [line.strip() for line in text.splitlines() if line.strip()]


def check_reference_content_rules(
    parsed_data: Dict[str, Any], source_file: str | None = None
) -> List[Dict[str, Any]]:
    del source_file
    issues: List[Dict[str, Any]] = []
    reference_texts = _reference_texts(parsed_data)

    for reference_text in reference_texts:
        if not reference_text:
            continue

        reference_kind_match = _REFERENCE_TYPE_PATTERN.search(reference_text)
        reference_kind = (
            reference_kind_match.group("kind") if reference_kind_match else ""
        )
        years = _extract_years(reference_text)
        two_digit_years = _extract_two_digit_years(reference_text)
        author_count = _count_authors(reference_text)

        if reference_kind == "J":
            if "，" in reference_text:
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 2,
                        "message": "[J] 文献包含全角逗号",
                        "suggestion": "改用英文逗号",
                        "original": "，",
                        "rule_id": "REF-J-001",
                        "position": {
                            "start_char": reference_text.find("，"),
                            "end_char": reference_text.find("，") + 1,
                        },
                    }
                )
            if "[J]" in reference_text and "[J]." not in reference_text:
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 2,
                        "message": "[J] 后缺少英文句点",
                        "suggestion": "改为 [J].",
                        "rule_id": "REF-J-003",
                    }
                )
            if not re.search(r"\d+\s*\(\s*\d+\s*\)", reference_text):
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 2,
                        "message": "[J] 文献缺少卷期号",
                        "suggestion": "补充卷号和期号，如 35(6)",
                        "rule_id": "REF-J-004",
                    }
                )
            if not re.search(r"\d{1,4}\s*-\s*\d{1,4}", reference_text):
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 2,
                        "message": "[J] 文献缺少页码",
                        "suggestion": "补充页码，如 18-21",
                        "rule_id": "REF-J-005",
                    }
                )
            if author_count > 2 and not re.search(
                r"等|etal\.", reference_text, re.IGNORECASE
            ):
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 2,
                        "message": "[J] 文献作者超过两位但未使用等或 et al.",
                        "suggestion": "作者超过两位时使用等或 et al.",
                        "rule_id": "REF-J-006",
                    }
                )
            if any(year > 2026 for year in years):
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 3,
                        "message": "[J] 文献年份晚于 2026",
                        "suggestion": "核对年份是否真实",
                        "rule_id": "REF-J-007",
                    }
                )
            if any(year < 1900 for year in years):
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 3,
                        "message": "[J] 文献年份早于 1900",
                        "suggestion": "核对年份是否正确",
                        "rule_id": "REF-J-009",
                    }
                )
            if not years and two_digit_years:
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 3,
                        "message": "[J] 文献年份只有两位数字",
                        "suggestion": "补全为四位年份",
                        "rule_id": "REF-J-011",
                    }
                )

        if reference_kind == "M":
            if any(year < 1900 for year in years):
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 3,
                        "message": "[M] 文献年份早于 1900",
                        "suggestion": "核对年份是否正确",
                        "rule_id": "REF-M-001",
                    }
                )
            if not years and two_digit_years:
                issues.append(
                    {
                        "issue_type": "reference_format",
                        "severity": 3,
                        "message": "[M] 文献年份只有两位数字",
                        "suggestion": "补全为四位年份",
                        "rule_id": "REF-M-002",
                    }
                )

    citations = {
        int(match.group("index"))
        for match in _CITATION_PATTERN.finditer(
            extract_text_from_parsed_data(parsed_data)
        )
    }
    reference_indices = {
        index
        for entry in detect_reference_entries(parsed_data)
        if (index := _entry_index(entry))
    }

    if citations and reference_indices:
        missing_in_references = sorted(citations - reference_indices)
        if missing_in_references:
            issues.append(
                {
                    "issue_type": "reference_consistency",
                    "severity": 3,
                    "message": "正文中引用了但文末未定义的参考文献",
                    "suggestion": "补充对应参考文献定义",
                    "rule_id": "REF-CONSIST-001",
                    "missing_references": missing_in_references,
                }
            )

        unused_references = sorted(reference_indices - citations)
        if unused_references:
            issues.append(
                {
                    "issue_type": "reference_consistency",
                    "severity": 2,
                    "message": "文末定义了但正文中从未引用的参考文献",
                    "suggestion": "删除未引用文献或在正文补充引用",
                    "rule_id": "REF-CONSIST-002",
                    "unused_references": unused_references,
                }
            )

    return issues
