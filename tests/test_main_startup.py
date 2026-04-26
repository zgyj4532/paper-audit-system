from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit import main


def test_run_skips_java_start_when_backend_is_local(monkeypatch):
    monkeypatch.setattr(main.settings, "RULE_AUDIT_BACKEND", "local")
    monkeypatch.setattr(main.shutil, "which", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "find_rust_executable", lambda: None)

    java_started = {"value": False}

    def fail_if_called(*_args, **_kwargs):
        java_started["value"] = True
        raise AssertionError("Java engine should not start when backend is local")

    monkeypatch.setattr(main, "start_java_process", fail_if_called)
    monkeypatch.setattr(main, "start_rust_process", lambda *args, **kwargs: None)
    monkeypatch.setattr(main.uvicorn, "run", lambda *args, **kwargs: (_ for _ in ()).throw(SystemExit(0)))

    with pytest.raises(SystemExit):
        main.run()

    assert java_started["value"] is False