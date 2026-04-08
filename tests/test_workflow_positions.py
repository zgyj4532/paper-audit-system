import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit.services.workflow import langgraph


class FakeClient:
    async def review_chunk(self, text, *, section_id=None, strictness=3, focus_areas=None):
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


@pytest.mark.asyncio
async def test_review_document_expands_issue_span_from_original(monkeypatch):
    monkeypatch.setattr(langgraph, "build_qwen_client", lambda: FakeClient())

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
