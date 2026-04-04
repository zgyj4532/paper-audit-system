import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..core.task_queue import TaskQueue
from ..config import settings

router = APIRouter()


@router.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: int):
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    row = await tq.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskQueue.row_to_dict(row)


@router.get("/api/v1/tasks")
async def list_tasks():
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    # Retrieve all tasks
    import aiosqlite
    async with aiosqlite.connect(str(settings.SQLITE_DB_PATH)) as db:
        cur = await db.execute("SELECT id, file_path, status, progress, result_path, error_message, created_at, current_stage, error_log, checkpoint_data, updated_at FROM tasks ORDER BY id DESC")
        rows = await cur.fetchall()
    return [TaskQueue.row_to_dict(r) for r in rows]


@router.get("/api/v1/tasks/{task_id}/progress")
async def get_task_progress(task_id: int):
    async def event_stream():
        tq = TaskQueue(str(settings.SQLITE_DB_PATH))
        await tq.init_db()
        for _ in range(120):
            row = await tq.get_task(task_id)
            if not row:
                yield f"event: error\ndata: {json.dumps({'detail': 'task not found'})}\n\n"
                return
            payload = TaskQueue.row_to_dict(row)
            yield f"data: {json.dumps({'progress': payload['progress'], 'status': payload['status'], 'current_stage': payload.get('current_stage')})}\n\n"
            if payload["status"] in {"done", "failed"}:
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
