from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(r"E:\github\paper-audit-system")
sys.path.insert(0, str(ROOT))
os.environ.pop("PAPER_AUDIT_FAST_LOCAL_ONLY", None)
os.environ["PAPER_AUDIT_FAST_LOCAL_ONLY"] = "0"

from python_service.paper_audit.core import rust_client
from python_service.paper_audit.services.workflow.langgraph import review_document

DOCX_PATH = ROOT / "18通信2_李良循_毕业论文 - 测试用.docx"


async def main():
    parse_result = await rust_client.parse(str(DOCX_PATH))
    parsed_data = parse_result.get("data", parse_result)
    review_result = await review_document(parsed_data)
    summary = review_result.get("summary", {})
    chunk_reviews = review_result.get("chunk_reviews", [])
    reference_verification = review_result.get("reference_verification", [])
    out_path = ROOT / "outputs" / "full_doc_review_summary.json"
    out_path.write_text(
        json.dumps(
            {
                "parse_metadata": parse_result.get("metadata", {}),
                "summary": summary,
                "chunk_count": len(review_result.get("chunks", [])),
                "reviewed_chunks": len(chunk_reviews),
                "reference_count": len(reference_verification),
                "first_5_chunk_counts": [item.get("issue_count", 0) for item in chunk_reviews[:5]],
                "last_5_chunk_counts": [item.get("issue_count", 0) for item in chunk_reviews[-5:]],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({
        "summary": summary,
        "chunk_count": len(review_result.get("chunks", [])),
        "reviewed_chunks": len(chunk_reviews),
        "reference_count": len(reference_verification),
        "output": str(out_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
