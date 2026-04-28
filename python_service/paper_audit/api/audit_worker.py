from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..config import settings
from ..core import rust_client
from ..core.task_queue import TaskQueue
from ..services.reporting import (
    compact_ai_review_for_report,
    cleanup_uploaded_source,
)
from .audit_common import _decode_checkpoint, _save_checkpoint

_task_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)


async def _process_task(task_id: int, file_path: str, *, resume: bool = False) -> None:
    async with _task_semaphore:
        tq = TaskQueue(str(settings.SQLITE_DB_PATH))
        await tq.init_db()

        absolute_file_path = str(Path(file_path).resolve())

        output_dir = settings.PYTHON_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"report_{task_id}.json"
        task_row = await tq.get_task(task_id)
        checkpoint = (
            _decode_checkpoint(TaskQueue.row_to_dict(task_row) if task_row else None)
            if resume
            else {}
        )

        try:
            await tq.update_task(
                task_id,
                status="processing",
                progress=10,
                current_stage=checkpoint.get("stage", "parsing"),
            )

            parse_result = checkpoint.get("parse_result")
            parsed_data = checkpoint.get("parsed_data")
            if not isinstance(parse_result, dict) or not isinstance(parsed_data, dict):
                parse_result = await rust_client.parse(absolute_file_path)
                parsed_data = parse_result.get("data", parse_result)
                checkpoint = {
                    "stage": "parsed",
                    "source_file": absolute_file_path,
                    "parse_result": parse_result,
                    "parsed_data": parsed_data,
                }
                await _save_checkpoint(
                    tq, task_id, checkpoint, current_stage="parsing", progress=25
                )
            else:
                checkpoint.setdefault("stage", "parsed")
                checkpoint.setdefault("source_file", absolute_file_path)
                await tq.update_task(task_id, current_stage="parsing", progress=25)

            await tq.update_task(task_id, progress=35, current_stage="analyzing")

            from ..core.langgraph import review_document

            ai_review = checkpoint.get("ai_review")
            if not isinstance(ai_review, dict):
                await tq.update_task(task_id, progress=55, current_stage="ai_review")
                ai_review = await review_document(parsed_data)
                checkpoint.update({"stage": "reviewed", "ai_review": ai_review})
                await _save_checkpoint(
                    tq, task_id, checkpoint, current_stage="ai_review", progress=55
                )
            else:
                await tq.update_task(task_id, progress=55, current_stage="ai_review")

            chunks = ai_review.get("chunks", [])
            chunk_reviews = ai_review.get("chunk_reviews", [])
            reference_results = ai_review.get("reference_verification", [])
            consistency_issues = ai_review.get("consistency_issues", [])
            await tq.update_task(task_id, progress=75, current_stage="reporting")

            report_payload = {
                "task_id": task_id,
                "source_file": absolute_file_path,
                "parse_result": parse_result,
                "chunks": chunks,
                "ai_review": ai_review,
                "java_review_raw": (
                    ai_review.get("java_review")
                    if isinstance(ai_review.get("java_review"), dict)
                    else None
                ),
                "reference_verification": reference_results,
                "chunk_reviews": chunk_reviews,
                "issues_count": (
                    sum(item.get("issue_count", 0) for item in chunk_reviews)
                    + sum(
                        1
                        for item in reference_results
                        if item.get("verdict") not in {"verified", None, ""}
                    )
                    + len(consistency_issues)
                ),
            }

            report_payload_for_json = dict(report_payload)
            report_payload_for_json["ai_review"] = compact_ai_review_for_report(
                ai_review
            )
            report_payload_for_json["chunk_reviews"] = report_payload_for_json[
                "ai_review"
            ].get("chunk_reviews", chunk_reviews)

            report_path.write_text(
                json.dumps(report_payload_for_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            checkpoint.update({"stage": "reported", "report_path": str(report_path)})
            await _save_checkpoint(
                tq, task_id, checkpoint, current_stage="reporting", progress=90
            )
            await tq.update_task(
                task_id,
                status="done",
                progress=100,
                result_path=str(report_path),
                current_stage="completed",
                error_message=None,
                checkpoint_data=json.dumps(checkpoint, ensure_ascii=False),
            )
            cleanup_uploaded_source(absolute_file_path)
        except Exception as exc:
            await tq.update_task(
                task_id,
                status="failed",
                progress=100,
                current_stage="failed",
                error_message=str(exc),
                error_log=str(exc),
                checkpoint_data=(
                    json.dumps(checkpoint, ensure_ascii=False) if checkpoint else None
                ),
            )


async def resume_recoverable_tasks() -> int:
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    rows = await tq.list_resumable_tasks()
    resumed = 0
    for row in rows:
        task = TaskQueue.row_to_dict(row)
        if not task:
            continue
        task_id = int(task["id"])
        file_path = str(task["file_path"])
        current_stage = str(task.get("current_stage") or "")
        if task.get("status") == "done" or current_stage == "completed":
            continue
        asyncio.create_task(_process_task(task_id, file_path, resume=True))
        resumed += 1
    return resumed
