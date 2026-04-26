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

[SCOPE]
本提示适用于常见论文与学术文档，包括但不限于学位论文、期刊论文、课程论文、开题报告、实验报告、设计说明书和综述类文档。
不同学校、期刊、学院和模板的结构存在差异，不能把某一种模板当成唯一标准。

[DOCUMENT_SPECIFIC_RULES]
1. 日期格式："2022年5月"、"2022年5月xx日" 这类写法属于规范日期格式，不要报日期格式错误。
2. 标题格式：封面、目录、摘要、作者简介、致谢、声明、页码、签名栏、附录、图表清单、参考文献题头等结构性文本，不要仅因为它们没有统一层级标题样式就报“标题格式不规范”。
3. 标题容错：像 "5.2 后续研究展望"、"作者简介"、"摘要I"、"郑 重 声 明" 这类可能带编号、空格或附加字符的结构标题，若在文档模板中可自洽存在，不要强行改成单一标题格式。
4. 目录与页码：目录中的条目编号、页码、章节层级展示属于结构性内容，不要把正常目录项误判为标题错误或格式错误。
5. 模板字段块：封面、签名栏、委员会名单、学院/专业/班级/学号/作者/指导教师等表单字段，允许按模板紧凑串联或用少量空格排版；如果它本来就是字段块，不要因为“没有分隔符”或“字段间空格较多”就强行判错。只有在正文里能明确确认字段粘连造成歧义时，才报格式问题。
6. 标点规则：如果文本已经符合论文规范，不要重复报“中英文标点混用”“缺少逗号/顿号/冒号分隔”“字段间空格过多”等问题。只有在能明确定位到真实不规范时才报错。
7. 术语斜体：普通软件名、平台名、通用英文术语不默认要求斜体；仅在生物学属名、种加词、参考文献中的外文期刊名、书名等明确规范场景才考虑斜体。
8. 术语与署名：软件名如 Blender、Unity3D、3ds Max 等一般不要求斜体；作者署名、指导教师、学院名称、页脚单位名、答辩委员会姓名等模板字段，优先按文档约定处理，不要默认改写格式。
9. 内容与格式：如果问题本质是逻辑、内容、结构或论证，而不是排版样式，不要误归为 format；应优先归类为 logic 或 reference。
10. 反例优先：若当前文本属于论文模板的固定结构块，且未明显违反规范，请默认不要制造格式问题。

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

输入："2022年5月"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："郑 重 声 明"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："5.2 后续研究展望"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："作者简介"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："学生姓名李良循学号1800301208"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："学生专业通信工程班级18通信2"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："答辩委员会主席单良评 阅 人汪晓峰"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："Unity3D"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
}}

输入："封面摘要"
输出：
{{
  "issues": [],
  "summary": {{"total_issues": 0, "max_severity": 0}}
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
