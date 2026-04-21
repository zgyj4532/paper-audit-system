import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit.services.workflow import langgraph


@pytest.fixture(autouse=True)
def _force_local_backend(monkeypatch):
    monkeypatch.setattr(langgraph.settings, "RULE_AUDIT_BACKEND", "local")


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


class FakeDuplicateTextClient:
    async def review_chunk(
        self, text, *, section_id=None, strictness=3, focus_areas=None
    ):
        issue = {
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
        return {"issues": [issue, dict(issue)]}


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


@pytest.mark.asyncio
async def test_review_document_skips_code_block(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("code blocks should skip AI and rule review")

    monkeypatch.setattr(langgraph, "build_qwen_client", fail_if_called)
    monkeypatch.setattr(langgraph, "check_text_rules", fail_if_called)

    parsed_data = {
        "sections": [
            {
                "id": 1,
                "raw_text": (
                    "using System.Collections;\n"
                    "using System.Collections.Generic;\n"
                    "using UnityEngine;\n"
                    "public class CameraControllor : MonoBehaviour\n"
                    "{\n"
                    "    public void Start() {}\n"
                    "}"
                ),
            }
        ]
    }

    result = await langgraph.review_document(parsed_data)
    chunk_reviews = result["chunk_reviews"]

    assert len(chunk_reviews) == 1
    assert chunk_reviews[0]["is_code_block"] is True
    assert chunk_reviews[0]["review_skipped"] == "code_block"
    assert chunk_reviews[0]["issue_count"] == 0
    assert result["consistency_issues"] == []


@pytest.mark.asyncio
async def test_review_document_skips_code_block_with_comment_markers(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("code blocks should skip AI and rule review")

    monkeypatch.setattr(langgraph, "build_qwen_client", fail_if_called)
    monkeypatch.setattr(langgraph, "check_text_rules", fail_if_called)

    parsed_data = {
        "sections": [
            {
                "id": 1,
                "raw_text": (
                    "using DG.Tweening;#调用DOTween插件\n"
                    "/// 相机动画\n"
                    "public class CameraControllor : MonoBehaviour\n"
                    "{\n"
                    "    public int Count = 0;#计数\n"
                    "}"
                ),
            }
        ]
    }

    result = await langgraph.review_document(parsed_data)
    chunk_reviews = result["chunk_reviews"]

    assert len(chunk_reviews) == 1
    assert chunk_reviews[0]["is_code_block"] is True
    assert chunk_reviews[0]["review_skipped"] == "code_block"
    assert chunk_reviews[0]["issue_count"] == 0


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
async def test_review_document_dedupes_duplicate_ai_issues(monkeypatch):
    monkeypatch.setattr(
        langgraph, "build_qwen_client", lambda: FakeDuplicateTextClient()
    )
    monkeypatch.setattr(langgraph, "check_text_rules", lambda text, focus_areas: [])

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
    assert len(chunk_reviews[0]["llm_issues"]) == 1
    assert len(chunk_reviews[0]["issues"]) == 1
    assert chunk_reviews[0]["issue_count"] == 1


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


@pytest.mark.asyncio
async def test_review_document_routes_to_java_http(monkeypatch):
    monkeypatch.setattr(langgraph.settings, "RULE_AUDIT_BACKEND", "java_http")

    called = {"value": False}

    async def fake_review_document_via_rules(parsed_data, source_file=None):
        called["value"] = True
        return {
            "backend": "java_http",
            "java_review": {"status": "ok"},
            "chunks": [],
            "chunk_reviews": [],
            "section_reviews": [],
            "reference_verification": [],
            "consistency_issues": [],
            "summary": {},
        }

    monkeypatch.setattr(
        langgraph, "review_document_via_rules", fake_review_document_via_rules
    )

    result = await langgraph.review_document({"sections": []})

    assert called["value"] is True
    assert result["backend"] == "java_http"


@pytest.mark.asyncio
async def test_review_document_hybrid_filters_java_reviewed_sections(monkeypatch):
    monkeypatch.setattr(langgraph.settings, "RULE_AUDIT_BACKEND", "hybrid")

    async def fake_review_document_java_http(parsed_data, source_file=None):
        return {
            "backend": "java_http",
            "java_review": {"issues": []},
            "chunks": [
                {"section_id": 1, "text": "java section"},
                {"section_id": 2, "text": "ai section"},
            ],
            "chunk_reviews": [
                {
                    "section_id": 1,
                    "kind": "section",
                    "text": "java section",
                    "is_table": False,
                    "issues": [
                        {
                            "issue_type": "format",
                            "severity": 3,
                            "message": "java issue",
                            "suggestion": "fix",
                            "original": "java section",
                            "position": {"section_id": 1},
                        }
                    ],
                    "issue_count": 1,
                    "backend": "java_http",
                    "java_issues": [],
                }
            ],
            "section_reviews": [
                {
                    "section_id": 1,
                    "kind": "section",
                    "text": "java section",
                    "is_table": False,
                    "issues": [
                        {
                            "issue_type": "format",
                            "severity": 3,
                            "message": "java issue",
                            "suggestion": "fix",
                            "original": "java section",
                            "position": {"section_id": 1},
                        }
                    ],
                    "issue_count": 1,
                    "backend": "java_http",
                    "java_issues": [],
                }
            ],
            "reference_verification": [],
            "consistency_issues": [],
            "summary": {
                "chunk_count": 2,
                "section_count": 1,
                "reference_count": 0,
                "chunk_issue_count": 1,
                "consistency_issue_count": 0,
                "java_issue_count": 1,
                "java_score_impact": 0,
            },
        }

    async def fake_review_document_local(parsed_data, source_file=None):
        assert [section["id"] for section in parsed_data["sections"]] == [2]
        return {
            "backend": "qwen",
            "chunks": [{"section_id": 2, "text": "ai section"}],
            "chunk_reviews": [
                {
                    "section_id": 2,
                    "kind": "section",
                    "text": "ai section",
                    "is_table": False,
                    "issues": [
                        {
                            "issue_type": "logic",
                            "severity": 2,
                            "message": "ai issue",
                            "suggestion": "fix",
                            "original": "ai section",
                            "position": {"section_id": 2},
                        }
                    ],
                    "issue_count": 1,
                    "backend": "qwen",
                    "local_issues": [],
                    "llm_issues": [],
                }
            ],
            "section_reviews": [
                {
                    "section_id": 2,
                    "kind": "section",
                    "text": "ai section",
                    "is_table": False,
                    "issues": [
                        {
                            "issue_type": "logic",
                            "severity": 2,
                            "message": "ai issue",
                            "suggestion": "fix",
                            "original": "ai section",
                            "position": {"section_id": 2},
                        }
                    ],
                    "issue_count": 1,
                    "backend": "qwen",
                    "local_issues": [],
                    "llm_issues": [],
                }
            ],
            "reference_verification": [],
            "consistency_issues": [],
            "summary": {
                "chunk_count": 1,
                "section_count": 1,
                "reference_count": 0,
                "chunk_issue_count": 1,
                "consistency_issue_count": 0,
                "qwen_worker_count": 1,
                "qwen_batch_size": 1,
            },
        }

    monkeypatch.setattr(langgraph, "_review_document_java_http", fake_review_document_java_http)
    monkeypatch.setattr(langgraph, "_review_document_local", fake_review_document_local)
    monkeypatch.setattr(langgraph, "check_consistency_rules", lambda parsed_data, source_file=None: [])

    parsed_data = {
        "sections": [
            {"id": 1, "raw_text": "java section"},
            {"id": 2, "raw_text": "ai section"},
        ]
    }

    result = await langgraph.review_document(parsed_data)

    assert result["backend"] == "hybrid"
    assert result["java_section_reviews"][0]["section_id"] == 1
    assert result["ai_section_reviews"][0]["section_id"] == 2
    assert [item["section_id"] for item in result["section_reviews"]] == [1, 2]
    assert result["summary"]["java_issue_count"] == 1
    assert result["summary"]["ai_chunk_issue_count"] == 1
