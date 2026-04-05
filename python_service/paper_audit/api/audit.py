from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from uuid import uuid4

from ..config import settings
from ..core import rust_client
from ..core.task_queue import TaskQueue

router = APIRouter()
_task_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)


def _decode_checkpoint(task: dict[str, Any] | None) -> dict[str, Any]:
    if not task:
        return {}
    raw = task.get("checkpoint_data")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def _save_checkpoint(
    tq: TaskQueue,
    task_id: int,
    checkpoint: dict[str, Any],
    *,
    current_stage: str,
    progress: int,
) -> None:
    await tq.update_task(
        task_id,
        current_stage=current_stage,
        progress=progress,
        checkpoint_data=json.dumps(checkpoint, ensure_ascii=False),
    )


async def _process_task(task_id: int, file_path: str, *, resume: bool = False) -> None:
    async with _task_semaphore:
        tq = TaskQueue(str(settings.SQLITE_DB_PATH))
        await tq.init_db()

        absolute_file_path = str(Path(file_path).resolve())

        output_dir = settings.PYTHON_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"report_{task_id}.json"
        zip_path = output_dir / f"task_{task_id}.zip"
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

            # Run AI review workflow (chunk review + reference verification)
            from ..core.langgraph import review_document

            ai_review = checkpoint.get("ai_review")
            if not isinstance(ai_review, dict):
                await tq.update_task(task_id, progress=55, current_stage="ai_review")
                ai_review = await review_document(parsed_data)
                checkpoint.update(
                    {
                        "stage": "reviewed",
                        "ai_review": ai_review,
                    }
                )
                await _save_checkpoint(
                    tq, task_id, checkpoint, current_stage="ai_review", progress=55
                )
            else:
                await tq.update_task(task_id, progress=55, current_stage="ai_review")

            chunks = ai_review.get("chunks", [])
            chunk_reviews = ai_review.get("chunk_reviews", [])
            reference_results = ai_review.get("reference_verification", [])
            consistency_issues = ai_review.get("consistency_issues", [])
            await tq.update_task(task_id, progress=75, current_stage="annotating")

            issues = parsed_data.get("sections", [])
            annotate_result = await rust_client.annotate(
                absolute_file_path,
                issues,
                output_filename=f"{task_id}_annotated.docx",
            )
            annotated_path = annotate_result.get("output_path")

            report_payload = {
                "task_id": task_id,
                "source_file": absolute_file_path,
                "parse_result": parse_result,
                "chunks": chunks,
                "ai_review": ai_review,
                "reference_verification": reference_results,
                "chunk_reviews": chunk_reviews,
                "annotated_path": annotated_path,
                "issues_count": sum(
                    item.get("issue_count", 0) for item in chunk_reviews
                )
                + sum(
                    1
                    for item in reference_results
                    if item.get("verdict") not in {"verified", None, ""}
                )
                + len(consistency_issues),
            }

            checkpoint.update(
                {
                    "stage": "annotated",
                    "annotated_path": annotated_path,
                    "report_path": str(report_path),
                    "zip_path": str(zip_path),
                }
            )
            await _save_checkpoint(
                tq, task_id, checkpoint, current_stage="annotating", progress=90
            )

            should_write_report_json = report_payload["issues_count"] > 0
            if should_write_report_json:
                report_path.write_text(
                    json.dumps(report_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            elif report_path.exists():
                report_path.unlink()

            # Generate a simple PDF summary report using PyMuPDF (fitz)
            try:
                import fitz

                pdf_path = output_dir / f"report_{task_id}.pdf"
                doc = fitz.open()
                page = doc.new_page()
                text = json.dumps(report_payload, ensure_ascii=False, indent=2)
                # write text with a modest font size
                page.insert_text((72, 72), text, fontsize=10)
                doc.save(str(pdf_path))
                doc.close()
            except Exception:
                pdf_path = None

            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                if annotated_path and Path(annotated_path).exists():
                    archive.write(annotated_path, arcname=Path(annotated_path).name)
                if report_path.exists():
                    archive.write(report_path, arcname=report_path.name)
                if pdf_path and Path(pdf_path).exists():
                    archive.write(pdf_path, arcname=Path(pdf_path).name)

            # Remove temporary Rust parse JSON if present
            try:
                temp_path = None
                if isinstance(parse_result, dict):
                    temp_path = parse_result.get("temp_output_path")
                if temp_path:
                    t = Path(str(temp_path))
                    if t.exists():
                        t.unlink()
            except Exception:
                pass

            await tq.update_task(
                task_id,
                status="done",
                progress=100,
                result_path=str(zip_path),
                current_stage="completed",
                error_message=None,
                checkpoint_data=json.dumps(checkpoint, ensure_ascii=False),
            )
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


@router.post("/api/v1/tasks/{task_id}/resume")
async def resume_task(task_id: int):
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    row = await tq.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    task = TaskQueue.row_to_dict(row)
    checkpoint = _decode_checkpoint(task)
    if not checkpoint:
        raise HTTPException(status_code=409, detail="checkpoint not available")
    if task.get("status") == "processing":
        raise HTTPException(status_code=409, detail="task already processing")
    asyncio.create_task(_process_task(task_id, str(task["file_path"]), resume=True))
    return {
        "task_id": task_id,
        "status": "resuming",
        "checkpoint_stage": checkpoint.get("stage"),
    }


@router.post("/api/v1/audit", status_code=202)
async def create_audit(
    file: UploadFile = File(...),
    audit_config: str | None = Form(None),
):
    upload_dir: Path = settings.PYTHON_UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    if file.content_type not in {
        None,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=400, detail="unsupported file type")

    config = {}
    if audit_config:
        try:
            config = json.loads(audit_config)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid audit_config")

    max_mb = int(config.get("max_file_size_mb", settings.MAX_FILE_SIZE_MB))
    content = await file.read()
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")

    # Save uploaded file using a UUID-prefixed filename to avoid overwriting
    safe_name = Path(file.filename).name
    dest = (upload_dir / f"{uuid4().hex}_{safe_name}").resolve()
    dest.write_bytes(content)

    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    task_id = await tq.create_task(str(dest))
    asyncio.create_task(_process_task(task_id, str(dest)))
    return {"task_id": task_id, "status": "pending"}
