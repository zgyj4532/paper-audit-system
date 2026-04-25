from __future__ import annotations

import logging
import os
import shlex
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger("paper_audit.startup")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_JAVA_PROJECT_ROOT = _PROJECT_ROOT / "engine-java"
_JAVA_LOG_PATH = _JAVA_PROJECT_ROOT / "logs" / "java.log"
_JAVA_READY_RETRY_ATTEMPTS = 8
_JAVA_READY_RETRY_DELAY_SECONDS = 0.75


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


def _wait_for_java_health(timeout_seconds: float = 30.0) -> bool:
    deadline = time.time() + timeout_seconds
    health_url = f"{str(settings.ENGINE_JAVA_BASE_URL).rstrip('/')}/api/v1/rules/health"

    while time.time() < deadline:
        try:
            response = httpx.get(health_url, timeout=2.0)
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("status") == "healthy":
                    logger.info(
                        "Java engine started successfully: %s",
                        str(settings.ENGINE_JAVA_BASE_URL).rstrip("/"),
                    )
                    return True
        except Exception:
            pass
        time.sleep(0.5)

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
        logger.error("Maven executable not found; cannot build Java engine")
        return False

    cmd = [*maven_cmd, "-q", "-DskipTests", "package"]
    logger.info("Building Java engine: %s", shlex.join(cmd))
    try:
        subprocess.run(cmd, cwd=str(_JAVA_PROJECT_ROOT), check=True)
        return True
    except subprocess.CalledProcessError:
        logger.exception("Failed to build Java engine")
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
            logger.error(
                "Maven executable not found when attempting to start Java engine"
            )
            return None

        cmd = [*maven_cmd, "-q", "-DskipTests", "spring-boot:run"]
        logger.info("Starting Java engine with Maven: %s", shlex.join(cmd))
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
            logger.exception(
                "Maven executable not found when attempting to start Java engine"
            )
            return None

    jar = find_java_executable()
    if jar is None:
        if skip_build:
            logger.info(
                "Java executable not found and skip_build=True; not starting Java service."
            )
            return None
        if not build_java():
            return None
        jar = find_java_executable()
        if jar is None:
            logger.error("Java executable still not found after build")
            return None

    cmd = ["java", "-jar", str(jar.resolve())]
    logger.info("Starting Java engine: %s", shlex.join(cmd))
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
        logger.exception("Java executable not found when attempting to start")
        return None


def build_rust(release: bool = True) -> bool:
    cmd = ["cargo", "build"]
    if release:
        cmd.append("--release")
    logger.info("Building Rust engine: %s", shlex.join(cmd))
    try:
        subprocess.run(cmd, cwd=str(_PROJECT_ROOT / "rust_engine"), check=True)
        return True
    except subprocess.CalledProcessError:
        logger.exception("Failed to build Rust engine")
        return False


def start_rust_process(
    skip_build: bool = False, release: bool = True
) -> Optional[subprocess.Popen]:
    exe = find_rust_executable()
    if exe is None:
        if skip_build:
            logger.info(
                "Rust executable not found and skip_build=True; not starting Rust service."
            )
            return None
        if not build_rust(release=release):
            return None
        exe = find_rust_executable()
        if exe is None:
            logger.error("Rust executable still not found after build")
            return None

    env = os.environ.copy()
    env["RUST_HTTP_PORT"] = str(settings.RUST_HTTP_PORT)

    logger.info("Starting Rust engine: %s", exe)
    try:
        return subprocess.Popen([str(exe.resolve())], env=env)
    except FileNotFoundError:
        logger.exception("Rust executable not found when attempting to start")
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


def wait_for_java_health(timeout_seconds: float = 30.0) -> bool:
    return _wait_for_java_health(timeout_seconds=timeout_seconds)
