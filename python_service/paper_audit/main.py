from __future__ import annotations

import argparse
import logging
import os
import shlex
import shutil
import platform
import signal
import subprocess
import sys
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI

from .config import settings

log = logging.getLogger("paper_audit.main")
_APP_START_TIME = time.time()

app = FastAPI(title="paper-audit-python-service")
_routes_loaded = False


@app.on_event("startup")
async def resume_checkpointed_tasks() -> None:
    try:
        from .api.audit import resume_recoverable_tasks

        await resume_recoverable_tasks()
    except Exception:
        log.exception("Failed to resume checkpointed tasks on startup")


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
        log.debug("Some API modules unavailable; skipping route registration.")


def _possible_rust_bins() -> list[Path]:
    base = Path("rust_engine")
    return [
        base / "target" / "release" / "paper-audit-rust.exe",
        base / "target" / "release" / "paper-audit-rust",
        base / "target" / "debug" / "paper-audit-rust.exe",
        base / "target" / "debug" / "paper-audit-rust",
    ]


def find_rust_executable() -> Optional[Path]:
    for candidate in _possible_rust_bins():
        if candidate.exists():
            return candidate
    return None


def build_rust(release: bool = True) -> bool:
    cmd = ["cargo", "build"]
    if release:
        cmd.append("--release")
    log.info("Building Rust engine: %s", shlex.join(cmd))
    try:
        subprocess.run(cmd, cwd="rust_engine", check=True)
        return True
    except subprocess.CalledProcessError:
        log.exception("Failed to build Rust engine")
        return False


def start_rust_process(
    skip_build: bool = False, release: bool = True
) -> Optional[subprocess.Popen]:
    exe = find_rust_executable()
    if exe is None:
        if skip_build:
            log.info(
                "Rust executable not found and skip_build=True; not starting Rust service."
            )
            return None
        if not build_rust(release=release):
            return None
        exe = find_rust_executable()
        if exe is None:
            log.error("Rust executable still not found after build")
            return None

    env = os.environ.copy()
    env["RUST_HTTP_PORT"] = str(settings.RUST_HTTP_PORT)

    log.info("Starting Rust engine: %s", exe)
    try:
        return subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    except FileNotFoundError:
        log.exception("Rust executable not found when attempting to start")
        return None


def _terminate_proc(proc: subprocess.Popen, timeout: float = 5.0) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run() -> None:
    include_routes()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-rust-build",
        action="store_true",
        help="Do not attempt to build Rust if binary missing",
    )
    parser.add_argument(
        "--no-rust", action="store_true", help="Do not start Rust engine at all"
    )
    parser.add_argument(
        "--rust-release",
        action="store_true",
        default=True,
        help="Build Rust in release mode",
    )
    args, _ = parser.parse_known_args()

    rust_proc: Optional[subprocess.Popen] = None
    if not args.no_rust:
        if shutil.which("cargo") or find_rust_executable():
            rust_proc = start_rust_process(
                skip_build=args.skip_rust_build, release=args.rust_release
            )
        else:
            log.info(
                "No cargo in PATH and no Rust binary found; skipping Rust engine start."
            )

    def _on_signal(signum, frame):
        log.info("Received signal %s, shutting down.", signum)
        if rust_proc:
            _terminate_proc(rust_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        uvicorn.run(app, host="127.0.0.1", port=int(settings.PYTHON_UVICORN_PORT))
    finally:
        if rust_proc:
            _terminate_proc(rust_proc)


if __name__ == "__main__":
    run()
