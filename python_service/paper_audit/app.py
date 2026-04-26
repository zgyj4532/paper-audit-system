from __future__ import annotations

from contextlib import asynccontextmanager
import ctypes
import logging
import os
import platform
import sys
import time
from ctypes import wintypes
from pathlib import Path

from fastapi import FastAPI

from .config import settings

logger = logging.getLogger("paper_audit.app")
_APP_START_TIME = time.time()
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PYTHON_LOG_PATH = _PROJECT_ROOT / "logs" / "python.log"
_routes_loaded = False


def _configure_python_file_logging() -> None:
    _PYTHON_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    already_configured = False
    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler_path = Path(getattr(handler, "baseFilename", ""))
            if handler_path.resolve() == _PYTHON_LOG_PATH.resolve():
                already_configured = True
                break

    if not already_configured:
        file_handler = logging.FileHandler(_PYTHON_LOG_PATH, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(threadName)s] %(levelname)s %(name)s -- %(message)s"
            )
        )
        root_logger.addHandler(file_handler)

    for logger_name in (
        "paper_audit",
        "paper_audit.app",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ):
        named_logger = logging.getLogger(logger_name)
        named_logger.setLevel(logging.INFO)
        named_logger.propagate = True


_configure_python_file_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    include_routes()
    try:
        from .api.audit import resume_recoverable_tasks

        await resume_recoverable_tasks()
    except Exception:
        logger.exception("Failed to resume checkpointed tasks on startup")

    yield


app = FastAPI(title="paper-audit-python-service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    system_info = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "cwd": str(Path.cwd()),
        "process_id": os.getpid(),
        "parallel_threads": int(os.environ.get("RUST_PARALLEL_THREADS", "4")),
        "uptime_seconds": round(time.time() - _APP_START_TIME, 2),
    }

    memory_usage_mb = None
    if sys.platform.startswith("win"):
        try:

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            result = ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            )
            if result:
                memory_usage_mb = round(counters.WorkingSetSize / (1024 * 1024), 2)
        except Exception:
            memory_usage_mb = None
    else:
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            memory_usage_mb = round(usage.ru_maxrss / 1024.0, 2)
        except Exception:
            memory_usage_mb = None

    return {
        "status": "healthy",
        "version": "0.1.0",
        "capabilities": [
            "docx_parse",
            "annotation",
            "task_queue",
            "reporting",
            "admin_tools",
        ],
        "python_port": int(settings.PYTHON_UVICORN_PORT),
        "rust_port": int(settings.RUST_HTTP_PORT),
        "java_port": int(settings.ENGINE_JAVA_HTTP_PORT),
        "java_base_url": str(settings.ENGINE_JAVA_BASE_URL),
        "system": {
            **system_info,
            "memory_usage_mb": memory_usage_mb,
        },
    }


def include_routes() -> None:
    global _routes_loaded
    if _routes_loaded:
        return

    try:
        from .api import admin, audit, download, tasks

        app.include_router(admin.router)
        app.include_router(audit.router)
        app.include_router(tasks.router)
        app.include_router(download.router)
        _routes_loaded = True
    except Exception:
        logger.debug("Some API modules unavailable; skipping route registration.")
