from __future__ import annotations

import argparse
import logging
import shutil
import signal
import subprocess
import sys
from typing import Optional

import uvicorn

from .app import app
from .config import settings
from .startup import (
    _port_is_open,
    _resolve_maven_command,
    _terminate_proc,
    find_java_executable,
    find_rust_executable,
    start_java_process,
    start_rust_process,
    wait_for_java_health,
)

log = logging.getLogger("paper_audit.main")


def run() -> None:
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
            if not wait_for_java_health():
                log.warning(
                    "Java HTTP port is open but health check did not become healthy before timeout"
                )
        elif _resolve_maven_command() or find_java_executable():
            java_proc = start_java_process(skip_build=args.skip_java_build)
            if java_proc is not None and not wait_for_java_health():
                log.warning(
                    "Java engine did not report healthy before timeout; audit requests may retry"
                )
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