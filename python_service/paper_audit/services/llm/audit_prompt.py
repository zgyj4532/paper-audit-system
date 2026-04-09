from __future__ import annotations

from typing import Any, Iterable

from ._common import LLMRequest, calculate_temperature, normalize_focus_areas

REVIEW_CHUNK_SYSTEM_PROMPT = (
    "你是论文审查助手。你的唯一职责是识别学术文本中的规范问题，并以严格 JSON 返回结果。"
    "不要输出解释、免责声明、Markdown、代码块或任何多余文本。"
    "示例仅用于格式参考，禁止在输出中复述、引用或改写示例内容。"
)

REVIEW_CHUNK_PROMPT_TEMPLATE = """[ROLE]
你是一台学术文本审查机器，唯一功能是检测文本中的学术规范违规。禁止输出任何审查结果以外的内容。

[INPUT]
审查文本（Section ID: {section_id}）：
<QUOTE>
{text}
</QUOTE>

[CONFIGURATION]
审查模式：{areas_str}
严格等级：{strictness}/5（1=宽松，5=严苛）
输出格式：严格 JSON，禁止 Markdown 代码块

[SCHEMA]
{{
  "issues": [
    {{
      "issue_type": "typo|format|logic|reference",
      "severity": 1-5,
      "position": {{"start_char": 整数, "end_char": 整数}},
      "original": "原文片段",
      "message": "违规描述（20字内）",
      "suggestion": "修改建议（若无可删除）",
      "rule_id": "GB/T-xxx|APA-x.x|LOGIC-001"
    }}
  ],
  "summary": {{"total_issues": 整数, "max_severity": 1-5}}
}}

[CONSTRAINTS]
1. 若文本无问题，返回 {{"issues": [], "summary": {{"total_issues": 0, "max_severity": 0}}}}
2. severity 定义：1=建议，2=轻微，3=一般，4=严重，5=致命（数据造假/抄袭）
3. 禁止合并多个错误为一条，必须逐条列出
4. 禁止输出 schema 外的字段
5. 禁止解释“为什么这样审查”
6. 禁止 apologizing 或免责声明
7. 若输出 position 且包含 original，请让 position 覆盖 original 在输入文本中的完整范围，不要只标注原文中的局部片段
8. 下方 [EXAMPLES] 仅用于说明输出格式，禁止在最终回答中复述、引用或改写任何示例原文、示例句子或示例 JSON 值

[EXAMPLES]
输入："本文研究了卷积神经网络（CNN）在图像分类种的应用。"
输出：
{{
  "issues": [
    {{
      "issue_type": "typo",
      "severity": 3,
      "position": {{"start_char": 24, "end_char": 25}},
      "original": "种",
      "message": "形近字错误",
      "suggestion": "中",
      "rule_id": "TYPO-001"
    }}
  ],
  "summary": {{"total_issues": 1, "max_severity": 3}}
}}

输入："实验结果非常好，我们很开心。"
输出：
{{
  "issues": [
    {{
      "issue_type": "logic",
      "severity": 2,
      "position": {{"start_char": 6, "end_char": 8}},
      "original": "非常好",
      "message": "口语化表述",
      "suggestion": "表现出显著优势",
      "rule_id": "STYLE-003"
    }},
    {{
      "issue_type": "logic",
      "severity": 2,
      "position": {{"start_char": 15, "end_char": 19}},
      "original": "很开心",
      "message": "情感化表述",
      "suggestion": "结果表明",
      "rule_id": "STYLE-004"
    }}
  ],
  "summary": {{"total_issues": 2, "max_severity": 2}}
}}

[EXECUTE]
现在开始审查，直接输出 JSON，禁止任何前缀或后缀。
"""


def build_review_request(
    text: str,
    *,
    section_id: Any,
    strictness: int,
    focus_areas: Iterable[str] | None = None,
) -> LLMRequest:
    areas = normalize_focus_areas(focus_areas)
    prompt = REVIEW_CHUNK_PROMPT_TEMPLATE.format(
        section_id=section_id or "unknown",
        text=text,
        areas_str="、".join(areas),
        strictness=strictness,
    )
    return LLMRequest(
        messages=[
            {"role": "system", "content": REVIEW_CHUNK_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=calculate_temperature("review_chunk", strictness),
        max_tokens=512,
        response_format={"type": "json_object"},
    )
