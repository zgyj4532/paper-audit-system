from __future__ import annotations

import re
from typing import Any, Dict, List

from .common import RuleIssue, extract_text_from_parsed_data
from .document import check_document_rules
from .references import check_reference_content_rules

_ABBREVIATION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z]{2,}[A-Za-z0-9]*|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)(?![A-Za-z0-9])"
)
_CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_REFERENCE_LINE_PATTERN = re.compile(
    r"^(?:\s*\[[0-9]+\]|\s*参考文献\b|\s*\d+\.|\s*\[[A-Z]\])"
)
_REFERENCE_CONTENT_PATTERN = re.compile(
    r"(?:\[J\]|\[M\]|\[D\]|\[C\]|\[P\]|\b(?:doi|et al\.)\b|\b\d{4}\b)",
    re.IGNORECASE,
)
_CODE_LINE_PATTERN = re.compile(
    r"^(?:\s*(?:```|//|/\*|\*|#|///)|\s*(?:using|import|from|public|private|protected|class|def|void|int|float|double|string|bool|namespace)\b|.*[{};].*)",
    re.IGNORECASE,
)
_CODE_TOKEN_PATTERN = re.compile(
    r"\b(?:using|import|class|def|return|void|public|private|protected|namespace)\b",
    re.IGNORECASE,
)


def _iter_audit_lines(parsed_data: Dict[str, Any]) -> List[str]:
    text = extract_text_from_parsed_data(parsed_data)
    lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _is_reference_line(line) or _is_code_line(line):
            continue
        lines.append(line)
    return lines


def _is_reference_line(line: str) -> bool:
    return bool(
        _REFERENCE_LINE_PATTERN.search(line) or _REFERENCE_CONTENT_PATTERN.search(line)
    )


def _is_code_line(line: str) -> bool:
    if not line:
        return False
    if _CODE_LINE_PATTERN.search(line):
        return True
    if "#" in line and not _CHINESE_CHAR_PATTERN.search(line):
        return True
    if _CODE_TOKEN_PATTERN.search(line) and not _CHINESE_CHAR_PATTERN.search(line):
        return True
    if line.count(";") >= 1 and not _CHINESE_CHAR_PATTERN.search(line):
        return True
    if re.search(r"\b[A-Za-z_][\w.]*\s*\(", line) and not _CHINESE_CHAR_PATTERN.search(
        line
    ):
        return True
    return False


def _contains_chinese(text: str) -> bool:
    return bool(_CHINESE_CHAR_PATTERN.search(text))


def _extract_defined_abbreviations(text: str) -> set[str]:
    definitions: set[str] = set()
    patterns = (
        re.compile(
            r"(?P<full>[\u4e00-\u9fff][^\n（）()]{1,40}?)\s*[（(]\s*(?P<abbr>[A-Z]{2,}[A-Za-z0-9]*)\s*[)）]"
        ),
        re.compile(
            r"(?P<abbr>[A-Z]{2,}[A-Za-z0-9]*)\s*[（(]\s*(?P<full>[^\n（）()]{2,40})\s*[)）]"
        ),
    )
    for pattern in patterns:
        for match in pattern.finditer(text):
            full = str(match.groupdict().get("full") or "")
            abbr = str(match.groupdict().get("abbr") or "")
            if abbr and _contains_chinese(full):
                definitions.add(abbr.upper())
    return definitions


def _find_abbreviation_candidates(text: str) -> set[str]:
    return {match.group(0).upper() for match in _ABBREVIATION_PATTERN.finditer(text)}


def _check_unexpanded_abbreviations(
    parsed_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    audit_lines = _iter_audit_lines(parsed_data)
    if not audit_lines:
        return issues

    audit_text = "\n".join(audit_lines)
    if not _contains_chinese(audit_text):
        return issues

    defined_abbreviations = _extract_defined_abbreviations(audit_text)
    if not defined_abbreviations:
        defined_abbreviations = set()

    candidates = _find_abbreviation_candidates(audit_text) - defined_abbreviations
    for abbreviation in sorted(candidates):
        if len(abbreviation) < 2:
            continue
        if abbreviation.isalpha() and abbreviation.islower():
            continue
        issues.append(
            RuleIssue(
                issue_type="logic",
                severity=1,
                message="英文缩写出现但未见中文全称",
                suggestion="首次出现时补充中文全称",
                rule_id="CONSIST-003",
                original=abbreviation,
            ).as_dict()
        )

    return issues


def check_consistency_rules(
    parsed_data: Dict[str, Any], source_file: str | None = None
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    abstract = str(parsed_data.get("abstract", "") or parsed_data.get("summary", ""))
    conclusion = str(parsed_data.get("conclusion", ""))
    if abstract and conclusion:
        abstract_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", abstract.lower()))
        conclusion_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", conclusion.lower()))
        if abstract_tokens and conclusion_tokens:
            overlap = len(abstract_tokens & conclusion_tokens) / max(
                len(abstract_tokens), len(conclusion_tokens)
            )
            if overlap < 0.15:
                issues.append(
                    RuleIssue(
                        issue_type="logic",
                        severity=2,
                        message="摘要与结论表述相似度偏低",
                        suggestion="检查结论是否与摘要目标一致",
                        rule_id="CONSIST-001",
                    ).as_dict()
                )

    issues.extend(_check_unexpanded_abbreviations(parsed_data))

    issues.extend(check_document_rules(parsed_data, source_file=source_file))
    issues.extend(check_reference_content_rules(parsed_data, source_file=source_file))

    return issues
