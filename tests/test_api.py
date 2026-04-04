import sys
import pathlib
import asyncio
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import aiosqlite
from httpx import ASGITransport, AsyncClient

# ensure project root is on sys.path for local imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit import main as pa_main
from python_service.paper_audit.config import settings


@pytest.mark.asyncio
async def test_health_endpoint_includes_system_info():
    pa_main.include_routes()
    app = pa_main.app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        resp = await ac.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "system" in data
        assert "memory_usage_mb" in data["system"]
        assert "parallel_threads" in data["system"]


@pytest.mark.asyncio
async def test_audit_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PYTHON_UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(settings, "PYTHON_OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", tmp_path / "tasks.db")

    async def fake_parse(file_path: str):
        return {"sections": [{"title": "intro"}], "styles": {}}

    async def fake_annotate(original_path: str, issues: list, output_filename: str | None = None):
        out_dir = settings.PYTHON_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / (output_filename or "annotated.docx")
        out_file.write_bytes(b"dummy docx")
        return {"success": True, "output_path": str(out_file), "stats": {"comments_injected": len(issues), "file_size_kb": 1}}

    async def fake_review_document(parsed_data: dict):
        return {
            "backend": "qwen",
            "chunks": [{"section_id": 1, "text": "intro"}],
            "chunk_reviews": [{"section_id": 1, "issues": [{"issue_type": "format", "severity": 1, "message": "ok", "suggestion": "none"}]}],
            "reference_verification": [{"reference": {"text": "[1] Example"}, "verdict": "verified", "reason": "mock", "retrieved": []}],
        }

    monkeypatch.setattr("python_service.paper_audit.core.rust_client.parse", fake_parse)
    monkeypatch.setattr("python_service.paper_audit.core.rust_client.annotate", fake_annotate)
    monkeypatch.setattr("python_service.paper_audit.core.langgraph.review_document", fake_review_document)

    # ensure routes are included (main.run() would do this in production)
    pa_main.include_routes()
    app = pa_main.app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        files = {"file": ("test.docx", b"dummy content")}
        resp = await ac.post("/api/v1/audit", files=files)
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data

        task_id = data["task_id"]

        # wait for background processing to finish
        for _ in range(30):
            status_resp = await ac.get(f"/api/v1/tasks/{task_id}")
            assert status_resp.status_code == 200
            task_data = status_resp.json()
            if task_data["status"] in {"done", "failed"}:
                break
            await asyncio.sleep(0.05)

        assert task_data["status"] == "done"
        assert task_data["progress"] == 100
        assert task_data["current_stage"] == "completed"
        assert "error_log" in task_data
        assert task_data["result_path"]

        report_resp = await ac.get(f"/api/v1/report/{task_id}")
        assert report_resp.status_code == 200
        report = report_resp.json()
        assert report["task_id"] == task_id
        assert report["annotated_path"]
        assert report["ai_review"]["backend"] == "qwen"

        download_resp = await ac.get(f"/api/v1/download/{task_id}?type=zip")
        assert download_resp.status_code == 200
        assert download_resp.headers["content-type"] in {
            "application/zip",
            "application/octet-stream",
            "application/x-zip-compressed",
        }

        pdf_resp = await ac.get(f"/api/v1/download/{task_id}?type=pdf")
        assert pdf_resp.status_code == 200


@pytest.mark.asyncio
async def test_report_requires_completed_task(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PYTHON_OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", tmp_path / "tasks.db")

    pa_main.include_routes()
    app = pa_main.app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        from python_service.paper_audit.core.task_queue import TaskQueue

        tq = TaskQueue(str(settings.SQLITE_DB_PATH))
        await tq.init_db()
        task_id = await tq.create_task(str(tmp_path / "dummy.docx"))

        resp = await ac.get(f"/api/v1/report/{task_id}")
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_admin_index_paper(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", tmp_path / "chroma_db")
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", tmp_path / "tasks.db")

    pa_main.include_routes()
    app = pa_main.app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        payload = {
            "id": "paper-001",
            "title": "Deep Learning for Testing",
            "authors": ["Alice", "Bob"],
            "year": 2026,
            "journal": "Journal of Testing",
            "doi": "10.1000/test.001",
            "source": "seed_data",
            "text": "Deep learning improves testing workflows.",
        }
        resp = await ac.post("/api/v1/admin/index_paper", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["paper_id"] == "paper-001"
        assert data["collection_name"] == settings.CHROMA_COLLECTION_NAME

        from python_service.paper_audit.services.vector.store import query_papers

        matches = query_papers("testing workflows improve with deep learning", n_results=1)
        assert matches
        assert matches[0]["id"] == "paper-001"


@pytest.mark.asyncio
async def test_admin_cleanup_and_archive(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    temp_dir = tmp_path / "temp"
    archives = tmp_path / "archives"
    db_path = tmp_path / "tasks.db"

    monkeypatch.setattr(settings, "PYTHON_UPLOAD_DIR", uploads)
    monkeypatch.setattr(settings, "PYTHON_OUTPUT_DIR", outputs)
    monkeypatch.setattr(settings, "PYTHON_TEMP_DIR", temp_dir)
    monkeypatch.setattr(settings, "ARCHIVE_DIR", archives)
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", db_path)

    uploads.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    old_ts = (datetime.now() - timedelta(days=40)).timestamp()

    old_upload = uploads / "old.docx"
    old_upload.write_bytes(b"upload")
    os.utime(old_upload, (old_ts, old_ts))

    temp_json = temp_dir / "rust_parse" / "sample_parsed.json"
    temp_json.parent.mkdir(parents=True, exist_ok=True)
    temp_json.write_text("{}", encoding="utf-8")

    old_report = outputs / "report_1.json"
    old_report.write_text("{}", encoding="utf-8")
    os.utime(old_report, (old_ts, old_ts))

    old_pdf = outputs / "report_1.pdf"
    old_pdf.write_bytes(b"pdf")
    os.utime(old_pdf, (old_ts, old_ts))

    pa_main.include_routes()
    app = pa_main.app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        cleanup_resp = await ac.post(
            "/api/v1/admin/cleanup",
            json={"upload_retention_days": 7, "report_retention_days": 30, "prune_completed_tasks": False, "dry_run": False},
        )
        assert cleanup_resp.status_code == 200
        cleanup = cleanup_resp.json()
        assert cleanup["files_deleted"] >= 3
        assert not old_upload.exists()
        assert not temp_json.exists()
        assert not old_report.exists()

        from python_service.paper_audit.core.task_queue import TaskQueue

        tq = TaskQueue(str(db_path))
        await tq.init_db()
        task_id = await tq.create_task(str(tmp_path / "paper.docx"))
        fresh_zip = outputs / "task_1.zip"
        with zipfile.ZipFile(fresh_zip, "w") as archive:
            archive.writestr("report_1.json", "{}")
        await tq.update_task(task_id, status="done", progress=100, result_path=str(fresh_zip), current_stage="completed")
        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", ((datetime.now() - timedelta(days=40)).isoformat(sep=" "), task_id))
            await db.commit()

        archive_resp = await ac.post("/api/v1/admin/archive", json={"older_than_days": 30, "prune_after_archive": False})
        assert archive_resp.status_code == 200
        archive = archive_resp.json()
        assert archive["archive_created"] is True
        assert archive["archived_tasks"] == 1
        assert Path(archive["archive_path"]).exists()
