from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from subprocess import Popen

ROOT = Path(r"E:\github\paper-audit-system")
sys.path.insert(0, str(ROOT))

from python_service.paper_audit.api.audit import resume_recoverable_tasks
from python_service.paper_audit.config import settings
from python_service.paper_audit.core.task_queue import TaskQueue

DOCX_PATH = ROOT / "18通信2_李良循_毕业论文 - 测试用.docx"
PARSE_JSON_PATH = ROOT / "outputs" / "rust_parse_test.json"
RUST_EXE = ROOT / "rust_engine" / "target" / "debug" / "paper-audit-rust.exe"
RUST_PORT = 8086


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


async def ensure_rust_server() -> None:
    if port_open(RUST_PORT):
        return
    env = os.environ.copy()
    env["RUST_HTTP_PORT"] = str(RUST_PORT)
    Popen([str(RUST_EXE)], cwd=str(RUST_EXE.parent), env=env)
    for _ in range(30):
        if port_open(RUST_PORT):
            return
        await asyncio.sleep(1)
    raise RuntimeError("Rust server did not start on port 8095")


async def main() -> None:
    await ensure_rust_server()

    parse_result = json.loads(PARSE_JSON_PATH.read_text(encoding="utf-8"))
    checkpoint = {
        "stage": "parsed",
        "source_file": str(DOCX_PATH),
        "parse_result": parse_result,
        "parsed_data": parse_result.get("data", parse_result),
    }

    tq = TaskQueue(str(settings.SQLITE_DB_PATH))
    await tq.init_db()
    task_id = await tq.create_task(str(DOCX_PATH))
    await tq.update_task(
        task_id,
        status="failed",
        progress=25,
        current_stage="parsing",
        error_message="simulated interruption",
        checkpoint_data=json.dumps(checkpoint, ensure_ascii=False),
    )

    resumed = await resume_recoverable_tasks()

    final_row = None
    for _ in range(180):
        row = await tq.get_task(task_id)
        final_row = TaskQueue.row_to_dict(row)
        if final_row and final_row.get("status") in {"done", "completed", "failed"}:
            if final_row.get("status") in {"done", "completed"}:
                break
        await asyncio.sleep(1)

    result_path = final_row.get("result_path") if final_row else None
    report_path = ROOT / "outputs" / f"report_{task_id}.json"

    print(json.dumps({
        "task_id": task_id,
        "resumed_count": resumed,
        "final_task": final_row,
        "result_zip_exists": bool(result_path and Path(result_path).exists()),
        "report_json_exists": report_path.exists(),
        "result_zip_path": result_path,
        "report_json_path": str(report_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
