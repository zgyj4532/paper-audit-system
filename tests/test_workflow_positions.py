import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit.services.workflow import langgraph


class FakeTextClient:
    async def review_chunk(
        self, text, *, section_id=None, strictness=3, focus_areas=None
    ):
        return {
            "issues": [
                {
                    "issue_type": "format",
                    "severity": 3,
                    "position": {
                        "start_char": 18,
                        "end_char": 20,
                    },
                    "original": "杨力老师以及他的学生闫珍锜学长",
                    "message": "称呼不规范，避免使用“学长”",
                    "suggestion": "杨力老师及其指导的学生闫珍锜",
                    "rule_id": "APA-4.03",
                }
            ]
        }


class FakeTableClient:
    def __init__(self):
        self.review_table_called = False

    async def review_table(
        self,
        table_rows,
        *,
        section_id=None,
        doc_type="学位论文",
        degree_level="学士",
        institution="中国计量大学",
        strictness=3,
    ):
        self.review_table_called = True
        return {
            "table_issues": [
                {
                    "issue_type": "placeholder_unchecked",
                    "severity": 5,
                    "field_name": "关键词",
                    "field_value": "关键词*",
                    "position": {
                        "section_id": section_id,
                        "table_index": 1,
                        "row": 1,
                        "col": 1,
                    },
                    "message": "必填字段未填写，仍为占位符",
                    "suggestion": "填写实际关键词",
                    "rule_id": "THESIS-FORMAT-001",
                    "auto_fixable": False,
                }
            ],
            "field_summary": {
                "total_fields": 2,
                "required_fields": 1,
                "filled_required": 0,
                "empty_required": 1,
                "format_errors": 0,
                "consistency_errors": 0,
            },
            "critical_gaps": ["关键词"],
        }


def test_split_into_chunks_expands_table_rows():
    parsed_data = {
        "sections": [
            {
                "id": 1,
                "is_table": True,
                "table_rows": [
                    ["关键词*", "密级*", "中图分类号*", "UDC"],
                    ["虚拟现实；图像拼接融合；Unity3D；全景图技术", "公开", "TP37", ""],
                    ["论文赞助*", "无"],
                ],
                "raw_text": "ignored when table_rows exist",
            }
        ]
    }

    chunks = langgraph.split_into_chunks(parsed_data)

    assert len(chunks) == 3
    assert chunks[0]["kind"] == "row"
    assert chunks[0]["table_index"] == 1
    assert chunks[0]["row_index"] == 1
    assert chunks[0]["cell_count"] == 4
    assert chunks[0]["cells"] == ["关键词*", "密级*", "中图分类号*", "UDC"]
    assert chunks[1]["row_index"] == 2
    assert chunks[1]["cells"][1] == "公开"
    assert chunks[2]["row_index"] == 3
    assert chunks[2]["cell_count"] == 2


@pytest.mark.asyncio
async def test_review_document_expands_issue_span_from_original(monkeypatch):
    monkeypatch.setattr(langgraph, "build_qwen_client", lambda: FakeTextClient())

    parsed_data = {
        "sections": [
            {
                "id": 25,
                "raw_text": (
                    "我首先要感谢我的论文指导老师，中国计量大学信息工程学院的杨力老师以及他的学生闫珍锜学长。"
                    "他们对我论文的研究方向做出了指导性的意见和帮助。"
                ),
            }
        ]
    }

    result = await langgraph.review_document(parsed_data)
    chunk_reviews = result["chunk_reviews"]

    assert len(chunk_reviews) == 1
    issue = chunk_reviews[0]["issues"][0]
    original = issue["original"]
    expected_start = chunk_reviews[0]["text"].find(original)

    assert expected_start >= 0
    assert issue["position"]["start_char"] == expected_start
    assert issue["position"]["end_char"] == expected_start + len(original)


@pytest.mark.asyncio
async def test_review_document_uses_table_prompt(monkeypatch):
    client = FakeTableClient()
    monkeypatch.setattr(langgraph, "build_qwen_client", lambda: client)

    parsed_data = {
        "sections": [
            {
                "id": 1,
                "is_table": True,
                "table_rows": [
                    ["关键词*", "密级*", "中图分类号*", "UDC"],
                    ["虚拟现实；图像拼接融合；Unity3D；全景图技术", "公开", "TP37", ""],
                ],
                "raw_text": "ignored when table_rows exist",
            }
        ]
    }

    result = await langgraph.review_document(parsed_data)
    chunk_reviews = result["chunk_reviews"]

    assert client.review_table_called is True
    assert len(chunk_reviews) == 1
    table_review = chunk_reviews[0]
    assert table_review["kind"] == "table"
    assert table_review["is_table"] is True
    assert table_review["issue_count"] == 1
    assert table_review["table_issues"][0]["field_name"] == "关键词"
    assert len(table_review["row_reviews"]) == 2
    assert table_review["row_reviews"][0]["row_index"] == 1
