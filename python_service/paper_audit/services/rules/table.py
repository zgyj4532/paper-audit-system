from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from .common import normalize_focus_areas


def _table_position(
    section_id: Any, table_index: Any, row_index: Any, col_index: Any
) -> Dict[str, Any]:
    return {
        "section_id": section_id,
        "table_index": table_index,
        "row": row_index,
        "col": col_index,
    }


def _add_table_issue(
    issues: List[Dict[str, Any]],
    *,
    issue_type: str,
    severity: int,
    field_name: str,
    field_value: str,
    position: Dict[str, Any],
    message: str,
    suggestion: str,
    rule_id: str,
    auto_fixable: bool,
) -> None:
    issues.append(
        {
            "issue_type": issue_type,
            "severity": max(1, min(int(severity), 5)),
            "field_name": field_name,
            "field_value": field_value,
            "position": position,
            "message": message,
            "suggestion": suggestion,
            "rule_id": rule_id,
            "auto_fixable": auto_fixable,
        }
    )


def check_table_rules(
    table_rows: List[Dict[str, Any]], focus_areas: Iterable[str] | None = None
) -> List[Dict[str, Any]]:
    active_areas = normalize_focus_areas(focus_areas)
    issues: List[Dict[str, Any]] = []

    if not table_rows:
        return issues

    if "format" not in active_areas and "logic" not in active_areas:
        return issues

    allowed_degree_levels = {
        "学士",
        "硕士",
        "博士",
    }
    allowed_confidentiality = {"公开", "内部", "秘密", "机密", "绝密"}

    for row in table_rows:
        if not isinstance(row, dict):
            continue
        section_id = row.get("section_id")
        table_index = row.get("table_index", 1)
        row_index = row.get("row_index", 0)
        cells = row.get("cells", [])
        if not isinstance(cells, list):
            continue

        for pair_start in range(0, len(cells), 2):
            field_name = str(cells[pair_start]).strip()
            field_value = (
                str(cells[pair_start + 1]).strip()
                if pair_start + 1 < len(cells)
                else ""
            )
            col_index = pair_start + 1
            position = _table_position(section_id, table_index, row_index, col_index)

            if not field_name:
                continue

            stripped_name = field_name.replace("*", "").strip()
            normalized_value = field_value.strip()

            if field_name.endswith("*") and not normalized_value:
                _add_table_issue(
                    issues,
                    issue_type="missing_required",
                    severity=5,
                    field_name=stripped_name or field_name,
                    field_value=field_value,
                    position=position,
                    message="必填字段未填写",
                    suggestion="补充完整字段值",
                    rule_id="THESIS-FORMAT-001",
                    auto_fixable=False,
                )
                continue

            if normalized_value and normalized_value == stripped_name:
                _add_table_issue(
                    issues,
                    issue_type="placeholder_unchecked",
                    severity=5,
                    field_name=stripped_name or field_name,
                    field_value=field_value,
                    position=position,
                    message="字段仍为占位符",
                    suggestion="填写实际内容",
                    rule_id="THESIS-FORMAT-002",
                    auto_fixable=False,
                )

            if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", normalized_value):
                _add_table_issue(
                    issues,
                    issue_type="format_error",
                    severity=3,
                    field_name=stripped_name or field_name,
                    field_value=field_value,
                    position=position,
                    message="日期格式非标准",
                    suggestion="改为 YYYY-MM-DD",
                    rule_id="ISO-8601",
                    auto_fixable=True,
                )

            if normalized_value == "四年":
                _add_table_issue(
                    issues,
                    issue_type="format_error",
                    severity=2,
                    field_name=stripped_name or field_name,
                    field_value=field_value,
                    position=position,
                    message="学制使用中文数字",
                    suggestion="改为 4年",
                    rule_id="THESIS-FORMAT-004",
                    auto_fixable=True,
                )

            if (
                stripped_name == "密级"
                and normalized_value
                and normalized_value not in allowed_confidentiality
            ):
                _add_table_issue(
                    issues,
                    issue_type="value_invalid",
                    severity=3,
                    field_name=stripped_name,
                    field_value=field_value,
                    position=position,
                    message="密级取值不规范",
                    suggestion="改为 公开、内部、秘密、机密或绝密",
                    rule_id="THESIS-FORMAT-004",
                    auto_fixable=True,
                )

            if (
                stripped_name == "学位级别"
                and normalized_value
                and normalized_value not in allowed_degree_levels
            ):
                _add_table_issue(
                    issues,
                    issue_type="value_invalid",
                    severity=3,
                    field_name=stripped_name,
                    field_value=field_value,
                    position=position,
                    message="学位级别取值不规范",
                    suggestion="改为 学士、硕士或博士",
                    rule_id="THESIS-FORMAT-004",
                    auto_fixable=True,
                )

            if "；" in normalized_value:
                _add_table_issue(
                    issues,
                    issue_type="format_error",
                    severity=2,
                    field_name=stripped_name or field_name,
                    field_value=field_value,
                    position=position,
                    message="表格字段使用全角分号",
                    suggestion="改用规范分隔符",
                    rule_id="THESIS-FORMAT-005",
                    auto_fixable=True,
                )

    return issues
