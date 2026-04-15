import sys
import pathlib
import pytest

# ensure project root is on sys.path for local imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit.core.task_queue import TaskQueue


@pytest.mark.asyncio
async def test_create_and_get_task(tmp_path):
    db_file = tmp_path / "tasks.db"
    tq = TaskQueue(str(db_file))
    await tq.init_db()
    task_id = await tq.create_task("/tmp/example.docx")
    row = await tq.get_task(task_id)
    assert row is not None
    task = TaskQueue.row_to_dict(row)
    assert task["id"] == task_id
    assert task["file_path"] == "/tmp/example.docx"
    assert task["status"] == "queued"
    assert task["progress"] == 0
    assert task["created_at"].endswith("+08:00")
    assert task["updated_at"].endswith("+08:00")
    await tq.update_task(
        task_id,
        status="done",
        progress=100,
        result_path="/tmp/result.zip",
        error_message=None,
    )
    updated = await tq.get_task(task_id)
    updated_task = TaskQueue.row_to_dict(updated)
    assert updated_task["status"] == "done"
    assert updated_task["progress"] == 100
    assert updated_task["result_path"] == "/tmp/result.zip"
    assert updated_task["created_at"].endswith("+08:00")
    assert updated_task["updated_at"].endswith("+08:00")
