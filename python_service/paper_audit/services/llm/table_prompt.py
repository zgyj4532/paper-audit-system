from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ._common import LLMRequest, calculate_temperature, json_pretty

TABLE_VALIDATION_SYSTEM_PROMPT = (
    "你是学位论文元数据表格审查专家。你的唯一职责是检测表格字段的规范性、完整性和一致性，"
    "并以严格 JSON 返回结果。不要输出解释、免责声明、Markdown、代码块或任何多余文本。"
)

TABLE_VALIDATION_PROMPT_TEMPLATE = """[ROLE]
你是一台学位论文元数据表格审查机器，专门检测表格字段是否符合学位论文格式规范。禁止输出审查结果以外的任何内容。

[INPUT]
待审查表格数据（Section ID: {section_id}）：
<TABLE_ROWS>
{table_json}
</TABLE_ROWS>

[CONTEXT]
文档类型：{doc_type}
学位级别：{degree_level}
所属机构：{institution}

[SCHEMA]
{{
  "table_issues": [
    {{
      "issue_type": "missing_required|format_error|value_invalid|consistency_error|placeholder_unchecked",
      "severity": 1-5,
      "field_name": "字段名",
      "field_value": "字段原始值",
      "position": {{"section_id": 整数, "table_index": 整数, "row": 整数, "col": 整数}},
      "message": "问题描述（30字内）",
      "suggestion": "修改建议",
      "rule_id": "GB/T-7714-x.x|THESIS-FORMAT-xxx|APA-x.x",
      "auto_fixable": true|false
    }}
  ],
  "field_summary": {{
    "total_fields": 整数,
    "required_fields": 整数,
    "filled_required": 整数,
    "empty_required": 整数,
    "format_errors": 整数,
    "consistency_errors": 整数
  }},
  "critical_gaps": ["缺失的关键字段列表"]
}}

[VALIDATION RULES]
1. 必填字段完整性检查：标记为 `*` 的字段必须有实际值，不能仅为标题本身
2. 占位符清除检查：字段值不能等于字段名（去除 `*` 后）
3. 代码字段规范：机构代码、分类号、学号等需有明确语义，不能孤立出现
4. 日期格式规范：禁止中文年月日，优先使用 `YYYY-MM-DD` 或 `YYYY`
5. 枚举值有效性：密级、学位类别、学位级别、学制等需符合规范取值
6. 列表字段规范：人名列表、关键词等需使用规范分隔符
7. 中英文一致性：并列题名、英文题名、字段语义需一致
8. 空字段检测：仅有标题无内容的字段需标记为占位符未填
9. 逻辑一致性：单位代码、地址、时间逻辑需核实

[CONSTRAINTS]
1. 若表格无问题，返回 {{"table_issues": [], "field_summary": {{...}}, "critical_gaps": []}}
2. severity 定义：1=建议优化，2=轻微格式问题，3=一般规范违规，4=重要信息缺失，5=关键数据错误或造假嫌疑
3. 禁止合并多个错误为一条，必须逐字段列出
4. 禁止输出 schema 外的字段
5. 禁止解释"为什么这样审查"
6. 禁止 apologizing 或免责声明
7. 下方 [EXAMPLES] 仅用于说明格式，禁止在最终回答中复述、引用或改写示例内容

[EXAMPLES]
输入字段：
`{{"字段": "关键词*", "值": "关键词*", "section_id": 1, "table_index": 1, "row": 1, "col": 1}}`
输出：
{{
  "table_issues": [
    {{
      "issue_type": "placeholder_unchecked",
      "severity": 5,
      "field_name": "关键词",
      "field_value": "关键词*",
      "position": {{"section_id": 1, "table_index": 1, "row": 1, "col": 1}},
      "message": "必填字段未填写，仍为占位符",
      "suggestion": "填写3-5个关键词，用分号分隔，如：虚拟现实；全景图；Unity3D",
      "rule_id": "THESIS-FORMAT-001",
      "auto_fixable": false
    }}
  ]
}}

[EXECUTE]
现在开始审查表格数据，直接输出 JSON，禁止任何前缀或后缀。
"""


def _normalize_table_rows(
    table_rows: Sequence[Dict[str, Any]], section_id: Any
) -> List[Dict[str, Any]]:
    normalized_rows: List[Dict[str, Any]] = []
    for row in table_rows:
        cells = row.get("cells") if isinstance(row, dict) else []
        if not isinstance(cells, list):
            cells = []
        normalized_rows.append(
            {
                "table_index": (
                    row.get("table_index", 1) if isinstance(row, dict) else 1
                ),
                "row_index": row.get("row_index", 0) if isinstance(row, dict) else 0,
                "cell_count": (
                    row.get("cell_count", len(cells))
                    if isinstance(row, dict)
                    else len(cells)
                ),
                "cells": ["" if cell is None else str(cell) for cell in cells],
                "section_id": (
                    row.get("section_id", section_id)
                    if isinstance(row, dict)
                    else section_id
                ),
            }
        )
    return normalized_rows


def build_table_validation_request(
    table_rows: Sequence[Dict[str, Any]],
    *,
    section_id: Any = None,
    doc_type: str = "学位论文",
    degree_level: str = "学士",
    institution: str = "中国计量大学",
    strictness: int = 3,
) -> LLMRequest:
    normalized_rows = _normalize_table_rows(table_rows, section_id)
    prompt = TABLE_VALIDATION_PROMPT_TEMPLATE.format(
        table_json=json_pretty(normalized_rows),
        section_id=section_id or "unknown",
        doc_type=doc_type,
        degree_level=degree_level,
        institution=institution,
    )
    return LLMRequest(
        messages=[
            {"role": "system", "content": TABLE_VALIDATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=calculate_temperature("table_validation", strictness),
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
