from __future__ import annotations

import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import settings
from ..core.task_queue import TaskQueue
from ..services.vector.store import index_paper

router = APIRouter()


class PaperIndexRequest(BaseModel):
    id: str | None = None
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    source: str = "user_upload"
    embedding_model: str = "simple-hash-embedding-v1"
    text: str | None = None
    abstract: str | None = None


class CleanupRequest(BaseModel):
    upload_retention_days: int = Field(default_factory=lambda: settings.UPLOAD_RETENTION_DAYS)
    report_retention_days: int = Field(default_factory=lambda: settings.REPORT_RETENTION_DAYS)
    prune_completed_tasks: bool = False
    dry_run: bool = False


class ArchiveRequest(BaseModel):
    older_than_days: int = Field(default_factory=lambda: settings.REPORT_RETENTION_DAYS)
    prune_after_archive: bool = False


def _ensure_path(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_age_days(path: Path) -> float:
    return (datetime.now().timestamp() - path.stat().st_mtime) / 86400.0


def _should_delete(path: Path, retention_days: int) -> bool:
    return path.exists() and _file_age_days(path) > retention_days


def _collect_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for pattern in patterns:
        files.extend(root.rglob(pattern))
    return [path for path in files if path.is_file()]


async def _list_completed_tasks_older_than(days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now() - timedelta(days=days)
    tasks: list[dict[str, Any]] = []
    async with aiosqlite.connect(str(settings.SQLITE_DB_PATH)) as db:
        cur = await db.execute(
            "SELECT id, file_path, status, progress, result_path, error_message, created_at, current_stage, error_log, checkpoint_data, updated_at FROM tasks WHERE status IN ('done', 'completed')"
        )
        rows = await cur.fetchall()
    for row in rows:
        task = TaskQueue.row_to_dict(row)
        updated_at = task.get("updated_at")
        try:
            if isinstance(updated_at, str):
                updated_dt = datetime.fromisoformat(updated_at)
            else:
                updated_dt = datetime.now()
        except Exception:
            updated_dt = datetime.now()
        if updated_dt <= cutoff:
            tasks.append(task)
    return tasks


@router.post("/api/v1/admin/index_paper")
async def admin_index_paper(payload: PaperIndexRequest) -> dict[str, Any]:
    try:
        return index_paper(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to index paper: {exc}") from exc


@router.post("/api/v1/admin/cleanup")
async def admin_cleanup(payload: CleanupRequest) -> dict[str, Any]:
    upload_dir = _ensure_path(settings.PYTHON_UPLOAD_DIR)
    output_dir = _ensure_path(settings.PYTHON_OUTPUT_DIR)
    temp_dir = _ensure_path(settings.PYTHON_TEMP_DIR)

    files_to_delete: list[Path] = []
    files_to_delete.extend(_collect_files(temp_dir, ("*_parsed.json",)))
    files_to_delete.extend([path for path in upload_dir.glob("*.*") if _should_delete(path, payload.upload_retention_days)])
    files_to_delete.extend(
        [
            path
            for path in output_dir.glob("report_*.json")
            if _should_delete(path, payload.report_retention_days)
        ]
    )
    files_to_delete.extend(
        [path for path in output_dir.glob("report_*.pdf") if _should_delete(path, payload.report_retention_days)]
    )
    files_to_delete.extend(
        [path for path in output_dir.glob("task_*.zip") if _should_delete(path, payload.report_retention_days)]
    )

    deleted_files: list[str] = []
    deleted_bytes = 0

    if not payload.dry_run:
        for path in files_to_delete:
            try:
                deleted_bytes += path.stat().st_size
                path.unlink(missing_ok=True)
                deleted_files.append(str(path))
            except Exception:
                continue

    pruned_tasks = 0
    if payload.prune_completed_tasks and not payload.dry_run:
        tasks_to_prune = await _list_completed_tasks_older_than(payload.report_retention_days)
        async with aiosqlite.connect(str(settings.SQLITE_DB_PATH)) as db:
            for task in tasks_to_prune:
                await db.execute("DELETE FROM tasks WHERE id = ?", (task["id"],))
                pruned_tasks += 1
            await db.commit()

    return {
        "dry_run": payload.dry_run,
        "upload_retention_days": payload.upload_retention_days,
        "report_retention_days": payload.report_retention_days,
        "files_marked": len(files_to_delete),
        "files_deleted": len(deleted_files),
        "deleted_bytes": deleted_bytes,
        "deleted_files": deleted_files[:25],
        "pruned_tasks": pruned_tasks,
    }


@router.post("/api/v1/admin/archive")
async def admin_archive(payload: ArchiveRequest) -> dict[str, Any]:
    archive_dir = _ensure_path(settings.ARCHIVE_DIR)
    output_dir = _ensure_path(settings.PYTHON_OUTPUT_DIR)
    tasks = await _list_completed_tasks_older_than(payload.older_than_days)
    if not tasks:
        return {
            "archive_created": False,
            "archive_path": None,
            "archived_tasks": 0,
            "task_ids": [],
        }

    archive_name = f"task_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    archive_path = archive_dir / archive_name

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for task in tasks:
            result_path = task.get("result_path")
            if not result_path:
                continue
            result_file = Path(result_path)
            if result_file.exists():
                bundle.write(result_file, arcname=result_file.name)
            report_json = output_dir / f"report_{task['id']}.json"
            if report_json.exists():
                bundle.write(report_json, arcname=report_json.name)
            report_pdf = output_dir / f"report_{task['id']}.pdf"
            if report_pdf.exists():
                bundle.write(report_pdf, arcname=report_pdf.name)

    if payload.prune_after_archive:
        async with aiosqlite.connect(str(settings.SQLITE_DB_PATH)) as db:
            for task in tasks:
                await db.execute("DELETE FROM tasks WHERE id = ?", (task["id"],))
            await db.commit()

    return {
        "archive_created": True,
        "archive_path": str(archive_path),
        "archived_tasks": len(tasks),
        "task_ids": [task["id"] for task in tasks],
        "prune_after_archive": payload.prune_after_archive,
    }