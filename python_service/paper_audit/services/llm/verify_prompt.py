from __future__ import annotations

from typing import Any, Dict, Sequence

from ._common import LLMRequest, calculate_temperature, json_pretty

VERIFY_REFERENCE_SYSTEM_PROMPT = (
    "你是学术文献核验系统。你的唯一职责是比较引用文本和检索结果，并以严格 JSON 返回核验结论。"
    "不要输出解释、免责声明、Markdown、代码块或任何多余文本。"
    "示例仅用于格式参考，禁止在输出中复述、引用或改写示例内容。"
)

VERIFY_REFERENCE_PROMPT_TEMPLATE = """[ROLE]
你是学术文献真伪核验系统，唯一任务是对比用户提供的引用文本与数据库检索结果，判定真伪。禁止输出判定结果以外的任何内容。

[INPUT]
待核验引用（原始文本）：
<REFERENCE>
{reference_text}
</REFERENCE>

数据库检索结果（Top-{k}）：
<RETRIEVED>
{retrieved_json}
</RETRIEVED>

[DECISION MATRIX]
| 条件 | 判定 | 置信度 |
|------|------|--------|
| 标题+作者+年份完全匹配 | verified | high |
| 标题相似度>0.9但年份/卷期不符 | needs_review | medium |
| 标题无法匹配或作者完全不同 | unverified | high |
| 检索结果为空 | unverified | low |

[SCHEMA]
{{
  "verdict": "verified|unverified|needs_review",
  "confidence": "high|medium|low",
  "matched_record": {{
    "title": "匹配到的标题",
    "authors": ["作者1", "作者2"],
    "year": 2024,
    "similarity_score": 0.0-1.0
  }},
  "discrepancies": [
    {{"field": "year|volume|pages|authors", "cited": "用户写的", "actual": "数据库的"}}
  ],
  "reason": "判定理由（30字内）",
  "risk_flags": ["year_mismatch", "author_disputed", "journal_not_found"]
}}

[CONSTRAINTS]
1. 禁止在 verified 时输出 discrepancies（必须为 []）
2. 禁止输出 schema 外的字段
3. 禁止解释检索算法或道歉
4. 禁止要求用户提供更多信息
5. 禁止对明显伪造的引用进行“善意推测”
6. 下方 [EXAMPLES] 仅用于说明输出格式，禁止在最终回答中复述、引用或改写任何示例原文、示例句子或示例 JSON 值

[EXAMPLES]
引用："Zhang et al., Nature, 2023, 关于量子计算"
检索：[{"title": "Quantum supremacy using a programmable superconducting processor", "authors": ["Arute et al."], "year": 2019}]
输出：
{{
  "verdict": "unverified",
  "confidence": "high",
  "matched_record": null,
  "discrepancies": [],
  "reason": "作者、年份、标题均不匹配，疑似虚构",
  "risk_flags": ["author_disputed", "year_mismatch"]
}}

引用："Ouyang et al., Training language models to follow instructions, 2022"
检索：[{"title": "Training language models to follow instructions with human feedback", "authors": ["Ouyang, L.", "Wu, J."], "year": 2022}]
输出：
{{
  "verdict": "verified",
  "confidence": "high",
  "matched_record": {{
    "title": "Training language models to follow instructions with human feedback",
    "authors": ["Ouyang, L.", "Wu, J."],
    "year": 2022,
    "similarity_score": 0.95
  }},
  "discrepancies": [],
  "reason": "标题、作者、年份完全匹配",
  "risk_flags": []
}}

[EXECUTE]
直接输出 JSON，禁止 Markdown 标记。
"""


def build_reference_request(
    reference_text: str, retrieved: Sequence[Dict[str, Any]]
) -> LLMRequest:
    prompt = VERIFY_REFERENCE_PROMPT_TEMPLATE.format(
        reference_text=reference_text.strip(),
        retrieved_json=json_pretty(list(retrieved)),
        k=len(retrieved),
    )
    return LLMRequest(
        messages=[
            {"role": "system", "content": VERIFY_REFERENCE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=calculate_temperature("verify_reference", 5),
        max_tokens=256,
        response_format={"type": "json_object"},
    )
