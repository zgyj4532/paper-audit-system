from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import json
import zipfile

from ..core.task_queue import TaskQueue
from ..config import settings
from ..services.artifacts import (
    ensure_task_docx_artifact,
    ensure_task_pdf_artifact,
    ensure_task_zip_artifact,
)

router = APIRouter()


@router.get("/api/v1/report/{task_id}")
async def get_report(task_id: int):
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    row = await tq.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    task = TaskQueue.row_to_dict(row)
    if task["status"] not in {"done", "completed"}:
        raise HTTPException(status_code=409, detail="task not complete")
    p, _ = ensure_task_zip_artifact(task_id, task)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="report not ready")
    try:
        with zipfile.ZipFile(p, "r") as archive:
            report_name = next(
                (name for name in archive.namelist() if name.endswith(".json")),
                None,
            )
            if not report_name:
                raise HTTPException(status_code=404, detail="report not ready")
            with archive.open(report_name) as handle:
                payload = json.loads(handle.read().decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=404, detail="report not ready") from exc
    return JSONResponse(payload)


@router.get("/api/v1/download/{task_id}")
async def download_result(
    task_id: int, type: str = Query("zip", pattern="^(zip|docx|pdf)$")
):
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    row = await tq.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    task = TaskQueue.row_to_dict(row)
    output_dir = settings.PYTHON_OUTPUT_DIR
    if type == "zip":
        p, _ = ensure_task_zip_artifact(task_id, task, output_dir)
    elif type == "pdf":
        p, _ = ensure_task_pdf_artifact(task_id, task, output_dir)
    else:
        p, _ = ensure_task_docx_artifact(task_id, task, output_dir)
    if not p or not Path(p).exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(p)
