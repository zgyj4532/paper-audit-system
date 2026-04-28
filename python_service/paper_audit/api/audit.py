from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..config import settings
from ..core.task_queue import TaskQueue
from .audit_common import _decode_checkpoint
from .audit_worker import _process_task

router = APIRouter()


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

    default_max_mb = getattr(
        settings, "MAX_FILE_SIZE_MB", getattr(settings, "MAX_UPLOAD_SIZE", 50)
    )
    max_mb = int(config.get("max_file_size_mb", default_max_mb))
    content = await file.read()
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")

    safe_name = Path(file.filename).name
    dest = (upload_dir / f"{uuid4().hex}_{safe_name}").resolve()
    dest.write_bytes(content)

    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    task_id = await tq.create_task(str(dest))
    asyncio.create_task(_process_task(task_id, str(dest)))
    return {"task_id": task_id, "status": "pending"}
