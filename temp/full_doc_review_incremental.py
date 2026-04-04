from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(r"E:\github\paper-audit-system")
sys.path.insert(0, str(ROOT))
os.environ["PAPER_AUDIT_FAST_LOCAL_ONLY"] = "0"

from python_service.paper_audit.core import rust_client
from python_service.paper_audit.services.llm import build_qwen_client, normalize_focus_areas
from python_service.paper_audit.services.workflow.langgraph import (
    _batch_items,
    _dedupe_issues,
    check_consistency_rules,
    check_text_rules,
    detect_reference_entries,
    verify_references,
    split_into_chunks,
)
from python_service.paper_audit.config import settings

DOCX_PATH = ROOT / "18通信2_李良循_毕业论文 - 测试用.docx"
PROGRESS_PATH = ROOT / "outputs" / "full_doc_review_progress.json"
SUMMARY_PATH = ROOT / "outputs" / "full_doc_review_summary.json"
BATCH_SIZE = max(1, int(getattr(settings, "LLM_QWEN_BATCH_SIZE", 4)))


async def main():
    parse_result = await rust_client.parse(str(DOCX_PATH))
    parsed_data = parse_result.get("data", parse_result)
    focus_areas = normalize_focus_areas(None)
    chunks = split_into_chunks(parsed_data)
    client = build_qwen_client()
    chunk_reviews = []

    for batch_index, batch in enumerate(_batch_items(chunks, BATCH_SIZE), start=1):
        local_issue_sets = [check_text_rules(chunk["text"], focus_areas) for chunk in batch]
        llm_issue_sets = await asyncio.gather(
            *[
                client.review_chunk(
                    chunk["text"],
                    section_id=chunk.get("section_id"),
                    strictness=3,
                    focus_areas=focus_areas,
                )
                for chunk in batch
            ]
        )
        for chunk, local_issues, qwen_result in zip(batch, local_issue_sets, llm_issue_sets):
            llm_issues = qwen_result.get("issues", []) if isinstance(qwen_result, dict) else []
            merged_issues = _dedupe_issues(local_issues + [issue for issue in llm_issues if isinstance(issue, dict)])
            chunk_reviews.append(
                {
                    "section_id": chunk.get("section_id"),
                    "text": chunk.get("text"),
                    "local_issues": local_issues,
                    "llm_issues": llm_issues,
                    "issues": merged_issues,
                    "issue_count": len(merged_issues),
                }
            )

        PROGRESS_PATH.write_text(
            json.dumps(
                {
                    "batch_size": BATCH_SIZE,
                    "processed_chunks": len(chunk_reviews),
                    "total_chunks": len(chunks),
                    "current_batch": batch_index,
                    "chunk_issue_count": sum(item.get("issue_count", 0) for item in chunk_reviews),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"processed_batch={batch_index} processed_chunks={len(chunk_reviews)}/{len(chunks)}")

    references = detect_reference_entries(parsed_data)
    reference_verification = await verify_references(references)
    consistency_issues = check_consistency_rules(parsed_data)

    summary = {
        "parse_metadata": parse_result.get("metadata", {}),
        "chunk_count": len(chunks),
        "reviewed_chunks": len(chunk_reviews),
        "reference_count": len(reference_verification),
        "chunk_issue_count": sum(item.get("issue_count", 0) for item in chunk_reviews),
        "consistency_issue_count": len(consistency_issues),
        "first_5_chunk_counts": [item.get("issue_count", 0) for item in chunk_reviews[:5]],
        "last_5_chunk_counts": [item.get("issue_count", 0) for item in chunk_reviews[-5:]],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
