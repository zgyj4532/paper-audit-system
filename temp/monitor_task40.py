from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(r"E:\github\paper-audit-system")
sys.path.insert(0, str(ROOT))

# ruff: noqa: E402
from python_service.paper_audit.config import settings
from python_service.paper_audit.core.task_queue import TaskQueue

TASK_ID = 40
REPORT = ROOT / "outputs" / "report_40.json"
ZIP = ROOT / "outputs" / "task_40.zip"


async def main() -> None:
    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    last = None
    while True:
        row = await tq.get_task(TASK_ID)
        task = TaskQueue.row_to_dict(row)
        state = {
            "status": task.get("status") if task else None,
            "current_stage": task.get("current_stage") if task else None,
            "progress": task.get("progress") if task else None,
            "result_path": task.get("result_path") if task else None,
            "report_exists": REPORT.exists(),
            "zip_exists": ZIP.exists(),
        }
        if state != last:
            print(json.dumps(state, ensure_ascii=False))
            last = state
        if state["status"] in {"done", "completed", "failed"}:
            break
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
