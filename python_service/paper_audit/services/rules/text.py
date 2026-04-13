from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from .common import (
    RuleIssue,
    add_issue,
    make_position,
    normalize_focus_areas,
    split_lines,
)

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


def check_text_rules(
    text: str, focus_areas: Iterable[str] | None = None
) -> List[Dict[str, Any]]:
    active_areas = normalize_focus_areas(focus_areas)
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
                        position=make_position(text, needle),
                        original=needle,
                        rule_id="TYPO-001",
                    ).as_dict()
                )

    if "format" in active_areas:
        for line in split_lines(text):
            for pattern, message, suggestion, rule_id in _ABSTRACT_LABEL_PATTERNS:
                if pattern.search(line):
                    add_issue(
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
                        position=make_position(text, needle),
                        original=needle,
                        rule_id="STYLE-001",
                    ).as_dict()
                )

    if "reference" in active_areas:
        has_reference_like_text = any(
            pattern.search(text) for pattern in _REFERENCE_PATTERNS
        )
        for line in split_lines(text):
            for pattern, message, suggestion, rule_id in _REFERENCE_FORMAT_PATTERNS:
                if pattern.search(line):
                    add_issue(
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
