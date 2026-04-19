from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import logging
import os
import shlex
import shutil
import platform
import socket
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

_routes_loaded = False
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_JAVA_PROJECT_ROOT = _PROJECT_ROOT / "engine-java"
_JAVA_LOG_PATH = _JAVA_PROJECT_ROOT / "logs" / "java.log"
_PYTHON_LOG_PATH = _PROJECT_ROOT / "logs" / "python.log"


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

    for logger_name in ("paper_audit", "paper_audit.main", "uvicorn", "uvicorn.error", "uvicorn.access"):
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
        log.exception("Failed to resume checkpointed tasks on startup")

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
        log.debug("Some API modules unavailable; skipping route registration.")


def _possible_rust_bins() -> list[Path]:
    base = _PROJECT_ROOT / "rust_engine"
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


def _possible_java_jars() -> list[Path]:
    configured = Path(settings.ENGINE_JAVA_JAR_PATH)
    candidates = [configured]
    if configured != configured.resolve():
        candidates.append(configured.resolve())
    target_dir = _JAVA_PROJECT_ROOT / "target"
    if target_dir.exists():
        candidates.extend(sorted(target_dir.glob("*.jar")))
    return candidates


def find_java_executable() -> Optional[Path]:
    for candidate in _possible_java_jars():
        if candidate.exists():
            return candidate
    return None


def _port_is_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_maven_command() -> Optional[list[str]]:
    for candidate_name in ("mvn", "mvn.cmd", "mvn.bat"):
        resolved = shutil.which(candidate_name)
        if not resolved:
            continue
        resolved_path = Path(resolved)
        if resolved_path.suffix.lower() in {".cmd", ".bat"}:
            return ["cmd", "/c", str(resolved_path)]
        return [str(resolved_path)]
    return None


def _open_java_log_stream():
    _JAVA_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _JAVA_LOG_PATH.open("a", encoding="utf-8")


def build_java() -> bool:
    maven_cmd = _resolve_maven_command()
    if maven_cmd is None:
        log.error("Maven executable not found; cannot build Java engine")
        return False

    cmd = [*maven_cmd, "-q", "-DskipTests", "package"]
    log.info("Building Java engine: %s", shlex.join(cmd))
    try:
        subprocess.run(cmd, cwd=str(_JAVA_PROJECT_ROOT), check=True)
        return True
    except subprocess.CalledProcessError:
        log.exception("Failed to build Java engine")
        return False


def start_java_process(skip_build: bool = False) -> Optional[subprocess.Popen]:
    java_target = str(settings.ENGINE_JAVA_START_MODE).strip().lower()
    env = os.environ.copy()
    env["ENGINE_JAVA_HTTP_PORT"] = str(settings.ENGINE_JAVA_HTTP_PORT)
    env["ENGINE_JAVA_GRPC_PORT"] = str(settings.ENGINE_JAVA_GRPC_PORT)
    env["ENGINE_JAVA_BASE_URL"] = str(settings.ENGINE_JAVA_BASE_URL)
    env["SPRING_PROFILES_ACTIVE"] = env.get("SPRING_PROFILES_ACTIVE", "local")

    if java_target == "run":
        maven_cmd = _resolve_maven_command()
        if maven_cmd is None:
            log.error("Maven executable not found when attempting to start Java engine")
            return None

        cmd = [*maven_cmd, "-q", "-DskipTests", "spring-boot:run"]
        log.info("Starting Java engine with Maven: %s", shlex.join(cmd))
        log_stream = _open_java_log_stream()
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_JAVA_PROJECT_ROOT),
                env=env,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
            )
            setattr(proc, "_log_stream", log_stream)
            return proc
        except FileNotFoundError:
            log_stream.close()
            log.exception("Maven executable not found when attempting to start Java engine")
            return None

    jar = find_java_executable()
    if jar is None:
        if skip_build:
            log.info(
                "Java executable not found and skip_build=True; not starting Java service."
            )
            return None
        if not build_java():
            return None
        jar = find_java_executable()
        if jar is None:
            log.error("Java executable still not found after build")
            return None

    cmd = ["java", "-jar", str(jar.resolve())]
    log.info("Starting Java engine: %s", shlex.join(cmd))
    log_stream = _open_java_log_stream()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_JAVA_PROJECT_ROOT),
            env=env,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
        )
        setattr(proc, "_log_stream", log_stream)
        return proc
    except FileNotFoundError:
        log_stream.close()
        log.exception("Java executable not found when attempting to start")
        return None


def build_rust(release: bool = True) -> bool:
    cmd = ["cargo", "build"]
    if release:
        cmd.append("--release")
    log.info("Building Rust engine: %s", shlex.join(cmd))
    try:
        subprocess.run(cmd, cwd=str(_PROJECT_ROOT / "rust_engine"), check=True)
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
        return subprocess.Popen([str(exe.resolve())], env=env)
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
    finally:
        log_stream = getattr(proc, "_log_stream", None)
        if log_stream is not None:
            try:
                log_stream.close()
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
    parser.add_argument(
        "--skip-java-build",
        action="store_true",
        help="Do not attempt to build Java if jar is missing",
    )
    parser.add_argument(
        "--no-java", action="store_true", help="Do not start Java engine at all"
    )
    args, _ = parser.parse_known_args()

    rust_proc: Optional[subprocess.Popen] = None
    java_proc: Optional[subprocess.Popen] = None
    if not args.no_rust:
        if _port_is_open("127.0.0.1", int(settings.RUST_HTTP_PORT)):
            log.info(
                "Rust HTTP port %s is already in use; assuming Rust engine is already running and skipping launch.",
                settings.RUST_HTTP_PORT,
            )
        elif shutil.which("cargo") or find_rust_executable():
            rust_proc = start_rust_process(
                skip_build=args.skip_rust_build, release=args.rust_release
            )
        else:
            log.info(
                "No cargo in PATH and no Rust binary found; skipping Rust engine start."
            )

    if not args.no_java:
        if _port_is_open("127.0.0.1", int(settings.ENGINE_JAVA_HTTP_PORT)):
            log.info(
                "Java HTTP port %s is already in use; assuming Java engine is already running and skipping launch.",
                settings.ENGINE_JAVA_HTTP_PORT,
            )
        elif _resolve_maven_command() or find_java_executable():
            java_proc = start_java_process(skip_build=args.skip_java_build)
        else:
            log.info(
                "No mvn in PATH and no Java jar found; skipping Java engine start."
            )

    def _on_signal(signum, frame):
        log.info("Received signal %s, shutting down.", signum)
        if rust_proc:
            _terminate_proc(rust_proc)
        if java_proc:
            _terminate_proc(java_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        uvicorn.run(app, host="127.0.0.1", port=int(settings.PYTHON_UVICORN_PORT))
    finally:
        if rust_proc:
            _terminate_proc(rust_proc)
        if java_proc:
            _terminate_proc(java_proc)


if __name__ == "__main__":
    run()
