import aiosqlite
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

TASK_COLUMNS = (
    "id",
    "file_path",
    "status",
    "progress",
    "result_path",
    "error_message",
    "created_at",
    "current_stage",
    "error_log",
    "checkpoint_data",
    "updated_at",
)

UTC_PLUS_8 = timezone(timedelta(hours=8))


def _now_utc8_iso() -> str:
    return datetime.now(UTC_PLUS_8).isoformat(sep=" ", timespec="seconds")


def _to_utc8_iso(value):
    if value is None or not isinstance(value, str):
        return value
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(UTC_PLUS_8).isoformat(sep=" ", timespec="seconds")


class TaskQueue:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_lock = asyncio.Lock()

    async def init_db(self):
        async with self._init_lock:
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT,
                        status TEXT,
                        progress INTEGER,
                        result_path TEXT,
                        error_message TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        current_stage TEXT,
                        error_log TEXT,
                        checkpoint_data TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """)
                async with db.execute("PRAGMA table_info(tasks)") as cursor:
                    columns = await cursor.fetchall()
                column_names = {row[1] for row in columns}
                if "checkpoint_data" not in column_names:
                    await db.execute(
                        "ALTER TABLE tasks ADD COLUMN checkpoint_data TEXT"
                    )
                await db.commit()

    async def create_task(self, file_path: str) -> int:
        now = _now_utc8_iso()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO tasks (file_path, status, progress, result_path, error_message, created_at, current_stage, error_log, checkpoint_data, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (file_path, "queued", 0, None, None, now, "queued", None, None, now),
            )
            await db.commit()
            return cur.lastrowid

    async def get_task(self, task_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT id, file_path, status, progress, result_path, error_message, created_at, current_stage, error_log, checkpoint_data, updated_at FROM tasks WHERE id = ?",
                (task_id,),
            )
            row = await cur.fetchone()
            return row

    async def list_resumable_tasks(self):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT id, file_path, status, progress, result_path, error_message, created_at, current_stage, error_log, checkpoint_data, updated_at FROM tasks WHERE status IN ('queued', 'processing', 'failed') AND checkpoint_data IS NOT NULL ORDER BY updated_at ASC"
            )
            return await cur.fetchall()

    async def update_task(
        self,
        task_id: int,
        *,
        status: str | None = None,
        progress: int | None = None,
        result_path: str | None = None,
        error_message: str | None = None,
        current_stage: str | None = None,
        error_log: str | None = None,
        checkpoint_data: str | None = None,
    ) -> None:
        updates = []
        values = []
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if progress is not None:
            updates.append("progress = ?")
            values.append(progress)
        if result_path is not None:
            updates.append("result_path = ?")
            values.append(result_path)
        if error_message is not None:
            updates.append("error_message = ?")
            values.append(error_message)
        if current_stage is not None:
            updates.append("current_stage = ?")
            values.append(current_stage)
        if error_log is not None:
            updates.append("error_log = ?")
            values.append(error_log)
        if checkpoint_data is not None:
            updates.append("checkpoint_data = ?")
            values.append(checkpoint_data)

        updates.append("updated_at = ?")
        values.append(_now_utc8_iso())

        if not updates:
            return

        values.append(task_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", values
            )
            await db.commit()

    async def delete_task(self, task_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            await db.commit()

    @staticmethod
    def row_to_dict(row):
        if row is None:
            return None
        data = dict(zip(TASK_COLUMNS, row))
        data["created_at"] = _to_utc8_iso(data.get("created_at"))
        data["updated_at"] = _to_utc8_iso(data.get("updated_at"))
        return data
