from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import json
import zipfile

from ..core.task_queue import TaskQueue
from ..config import settings

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
    result_path = task["result_path"]
    if not result_path:
        raise HTTPException(status_code=404, detail="report not ready")
    p = Path(result_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="file missing")
    with zipfile.ZipFile(p, "r") as archive:
        report_name = next((name for name in archive.namelist() if name.endswith(".json")), None)
        if not report_name:
            raise HTTPException(status_code=404, detail="report not ready")
        with archive.open(report_name) as handle:
            payload = json.loads(handle.read().decode("utf-8"))
    return JSONResponse(payload)


@router.get("/api/v1/download/{task_id}")
async def download_result(task_id: int, type: str = Query("zip", pattern="^(zip|docx|pdf)$")):
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    row = await tq.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    task = TaskQueue.row_to_dict(row)
    result_path = task["result_path"]
    if not result_path:
        raise HTTPException(status_code=404, detail="result not ready")
    result_file = Path(result_path)
    output_dir = settings.PYTHON_OUTPUT_DIR
    if type == "zip":
        p = result_file
    elif type == "pdf":
        p = output_dir / f"report_{task_id}.pdf"
    else:
        p = None
        if result_file.exists():
            try:
                with zipfile.ZipFile(result_file, "r") as archive:
                    docx_name = next((name for name in archive.namelist() if name.endswith("_annotated.docx")), None)
                    if docx_name:
                        extracted = output_dir / docx_name
                        extracted.parent.mkdir(parents=True, exist_ok=True)
                        extracted.write_bytes(archive.read(docx_name))
                        p = extracted
            except Exception:
                p = None
        if p is None:
            try:
                with open(output_dir / f"report_{task_id}.json", "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                annotated_path = payload.get("annotated_path")
                if annotated_path:
                    p = Path(str(annotated_path))
            except Exception:
                p = None
    if not p or not Path(p).exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(p)
