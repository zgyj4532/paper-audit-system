from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

DEFAULT_FOCUS_AREAS = ("typo", "format", "logic", "reference")

_COLLOQUIAL_PATTERNS = (
    ("非常好", "表现出显著优势"),
    ("很开心", "结果表明"),
    ("挺好的", "表现良好"),
    ("听说", "已有研究表明"),
    ("basically", "本质上"),
)

_TYPO_PATTERNS = (
    ("图像分类种", "图像分类中"),
    ("的的", "的"),
    ("，，", "，"),
    ("。。", "。"),
)

_REFERENCE_PATTERNS = (
    re.compile(r"\[\d+\]\s*[^\n]+"),
    re.compile(r"\b\d{4}\b"),
)

_ABSTRACT_LABEL_PATTERNS = (
    (
        re.compile(r"^Abstract:[^\s]", re.IGNORECASE),
        "摘要标题后缺少空格",
        "改为 Abstract: ",
        "FORMAT-004",
    ),
    (
        re.compile(r"^Keywords:[^\s]", re.IGNORECASE),
        "关键词标题后缺少空格",
        "改为 Keywords: ",
        "FORMAT-006",
    ),
)

_REFERENCE_FORMAT_PATTERNS = (
    (
        re.compile(r"(?<!\[)[A-Z]\]\."),
        "参考文献类型标记缺少左括号",
        "补全为 [D]. / [J]. / [C].",
        "REF-002",
    ),
    (
        re.compile(r"\[\[[A-Z]\]\."),
        "参考文献类型标记括号重复",
        "删除多余的左括号",
        "REF-003",
    ),
    (
        re.compile(r"Keywords:[A-Za-z]"),
        "Keywords 后缺少空格",
        "改为 Keywords: ",
        "FORMAT-003",
    ),
    (
        re.compile(r"Abstract:[A-Za-z]"),
        "Abstract 后缺少空格",
        "改为 Abstract: ",
        "FORMAT-004",
    ),
    (
        re.compile(r"[A-Za-z]{2,};[A-Za-z]{2,}"),
        "英文关键词之间缺少空格",
        "在分号后补空格",
        "FORMAT-005",
    ),
)


@dataclass(slots=True)
class RuleIssue:
    issue_type: str
    severity: int
    message: str
    suggestion: str | None = None
    position: Dict[str, int] | None = None
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


def _normalize_focus_areas(focus_areas: Iterable[str] | None) -> set[str]:
    return {
        str(area).strip()
        for area in (focus_areas or DEFAULT_FOCUS_AREAS)
        if str(area).strip()
    }


def _make_position(text: str, needle: str) -> Dict[str, int]:
    start = text.find(needle)
    if start < 0:
        return {"start_char": 0, "end_char": min(len(text), len(needle))}
    return {"start_char": start, "end_char": start + len(needle)}


def _add_issue(
    issues: List[Dict[str, Any]],
    *,
    issue_type: str,
    severity: int,
    message: str,
    suggestion: str | None = None,
    text: str | None = None,
    needle: str | None = None,
    rule_id: str | None = None,
):
    issues.append(
        RuleIssue(
            issue_type=issue_type,
            severity=severity,
            message=message,
            suggestion=suggestion,
            position=_make_position(text, needle) if text and needle else None,
            original=needle,
            rule_id=rule_id,
        ).as_dict()
    )


def _split_lines(text: str) -> List[str]:
    return [line for line in (part.strip() for part in text.splitlines()) if line]


def extract_text_from_parsed_data(parsed_data: Dict[str, Any]) -> str:
    sections = parsed_data.get("sections", []) if isinstance(parsed_data, dict) else []
    text_parts: List[str] = []
    for section in sections:
        if isinstance(section, dict):
            raw_text = section.get("raw_text") or section.get("text")
            if raw_text:
                text_parts.append(str(raw_text))
    return "\n".join(text_parts)


def check_text_rules(
    text: str, focus_areas: Iterable[str] | None = None
) -> List[Dict[str, Any]]:
    active_areas = _normalize_focus_areas(focus_areas)
    issues: List[Dict[str, Any]] = []

    if "typo" in active_areas:
        for needle, suggestion in _TYPO_PATTERNS:
            if needle in text:
                issues.append(
                    RuleIssue(
                        issue_type="typo",
                        severity=3,
                        message="疑似错别字或重复标点",
                        suggestion=suggestion,
                        position=_make_position(text, needle),
                        original=needle,
                        rule_id="TYPO-001",
                    ).as_dict()
                )

    if "format" in active_areas:
        for line in _split_lines(text):
            for pattern, message, suggestion, rule_id in _ABSTRACT_LABEL_PATTERNS:
                if pattern.search(line):
                    _add_issue(
                        issues,
                        issue_type="format",
                        severity=2,
                        message=message,
                        suggestion=suggestion,
                        text=text,
                        needle=line,
                        rule_id=rule_id,
                    )

        if re.search(r"[A-Za-z]+[，。；：、]", text):
            issues.append(
                RuleIssue(
                    issue_type="format",
                    severity=2,
                    message="中英文标点可能混用",
                    suggestion="统一为中文学术写作标点",
                    rule_id="FORMAT-001",
                ).as_dict()
            )
        if "Fig." in text or "Table" in text or "Eq." in text:
            issues.append(
                RuleIssue(
                    issue_type="format",
                    severity=2,
                    message="英文图表缩写出现在正文中",
                    suggestion="统一中文图表编号格式",
                    rule_id="FORMAT-002",
                ).as_dict()
            )

    if "logic" in active_areas:
        lowered_text = text.lower()
        for needle, suggestion in _COLLOQUIAL_PATTERNS:
            if needle.lower() in lowered_text:
                issues.append(
                    RuleIssue(
                        issue_type="logic",
                        severity=2,
                        message="口语化或情绪化表述",
                        suggestion=suggestion,
                        position=_make_position(text, needle),
                        original=needle,
                        rule_id="STYLE-001",
                    ).as_dict()
                )

    if "reference" in active_areas:
        has_reference_like_text = any(
            pattern.search(text) for pattern in _REFERENCE_PATTERNS
        )
        for line in _split_lines(text):
            for pattern, message, suggestion, rule_id in _REFERENCE_FORMAT_PATTERNS:
                if pattern.search(line):
                    _add_issue(
                        issues,
                        issue_type="reference",
                        severity=3,
                        message=message,
                        suggestion=suggestion,
                        text=text,
                        needle=line,
                        rule_id=rule_id,
                    )
        if (
            has_reference_like_text
            and "参考文献" in text
            and not re.search(r"\[[0-9]+\].+\d{4}", text)
        ):
            issues.append(
                RuleIssue(
                    issue_type="reference",
                    severity=3,
                    message="参考文献格式可能不完整",
                    suggestion="补全作者、年份、题名、期刊和页码",
                    rule_id="REF-001",
                ).as_dict()
            )
        if re.search(r"\[[0-9]+\][^\n]*[A-Za-z].*?\d{4}", text) and re.search(
            r"(?<!\[)[A-Z]\]\.|\[\[[A-Z]\]\.", text
        ):
            issues.append(
                RuleIssue(
                    issue_type="reference",
                    severity=3,
                    message="参考文献类型标记格式异常",
                    suggestion="统一使用 [D]、[J]、[C] 等规范格式",
                    rule_id="REF-004",
                ).as_dict()
            )

    return issues


def check_consistency_rules(parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    text = extract_text_from_parsed_data(parsed_data)
    lowered_text = text.lower()

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

    if "cnn" in lowered_text and "卷积神经网络" not in text:
        issues.append(
            RuleIssue(
                issue_type="logic",
                severity=1,
                message="缩写出现但未见中文全称",
                suggestion="首次出现时补充中文全称",
                rule_id="CONSIST-002",
            ).as_dict()
        )

    return issues


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
