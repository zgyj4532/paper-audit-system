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
    assert row[0] == task_id
    assert row[1] == "/tmp/example.docx"
    assert row[2] == "queued"
    assert row[3] == 0
    await tq.update_task(
        task_id,
        status="done",
        progress=100,
        result_path="/tmp/result.zip",
        error_message=None,
    )
    updated = await tq.get_task(task_id)
    assert updated[2] == "done"
    assert updated[3] == 100
    assert updated[4] == "/tmp/result.zip"
