"""
Readiness assessment tests.

Two readiness signals protect a release:

* the runtime handshake — the React UI calls ``frontend_ready`` once mounted and
  interactive, which (when requested) writes a marker file a supervisor waits on;
* the release gate — a tagged release must never pass without a frozen artifact
  being exercised, so the packaged gate is fail-closed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


def test_frontend_ready_writes_supervisor_marker(tmp_path, monkeypatch):
    marker = tmp_path / "previewgen.ready"
    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(marker))

    api = DesktopApi()
    try:
        result = api.frontend_ready()
        assert result["ok"] is True
        assert result["value"] == "ready"
        assert marker.is_file()
        assert marker.read_text(encoding="utf-8") == "READY\n"
    finally:
        api.cleanup()


def test_frontend_ready_writes_render_evidence(tmp_path, monkeypatch):
    marker = tmp_path / "render_ready.json"
    monkeypatch.setenv("PREVIEWGEN_RENDER_MARKER", str(marker))

    api = DesktopApi()
    api._window = object()
    monkeypatch.setattr(
        api,
        "_evaluate_js_bounded",
        lambda _window, _script, _timeout: json.dumps(
            {
                "rootChildCount": 3,
                "rootWidth": 1400,
                "rootHeight": 900,
                "textLength": 42,
            }
        ),
    )
    try:
        result = api.frontend_ready()
        assert result["ok"] is True
        evidence = json.loads(marker.read_text(encoding="utf-8"))
        assert evidence == {
            "ok": True,
            "rootChildCount": 3,
            "rootWidth": 1400,
            "rootHeight": 900,
            "textLength": 42,
            "error": None,
        }
    finally:
        api.cleanup()


def test_frontend_ready_records_an_empty_render_root(tmp_path, monkeypatch):
    marker = tmp_path / "render_ready.json"
    monkeypatch.setenv("PREVIEWGEN_RENDER_MARKER", str(marker))

    api = DesktopApi()
    api._window = object()
    monkeypatch.setattr(
        api,
        "_evaluate_js_bounded",
        lambda _window, _script, _timeout: json.dumps(
            {
                "rootChildCount": 0,
                "rootWidth": 1400,
                "rootHeight": 900,
                "textLength": 0,
            }
        ),
    )
    try:
        assert api.frontend_ready()["ok"] is True
        evidence = json.loads(marker.read_text(encoding="utf-8"))
        assert evidence["ok"] is False
        assert evidence["error"] == "RENDER_ROOT_EMPTY"
    finally:
        api.cleanup()


def test_frontend_ready_records_a_render_evaluation_timeout(tmp_path, monkeypatch):
    marker = tmp_path / "render_ready.json"
    monkeypatch.setenv("PREVIEWGEN_RENDER_MARKER", str(marker))

    api = DesktopApi()
    api._window = object()
    monkeypatch.setattr(
        api,
        "_evaluate_js_bounded",
        lambda _window, _script, _timeout: None,
    )
    try:
        assert api.frontend_ready()["ok"] is True
        evidence = json.loads(marker.read_text(encoding="utf-8"))
        assert evidence["ok"] is False
        assert evidence["error"] == "RENDER_EVALUATION_TIMEOUT"
    finally:
        api.cleanup()


def test_frontend_ready_without_marker_is_harmless(monkeypatch):
    monkeypatch.delenv("PREVIEWGEN_READY_MARKER", raising=False)

    api = DesktopApi()
    try:
        result = api.frontend_ready()
        assert result == {"ok": True, "value": "ready", "error": None}
    finally:
        api.cleanup()


def test_release_gate_is_fail_closed_without_frozen_artifact():
    """With the gate active but no ``PREVIEWGEN_BINARY``, the packaged gate fails."""
    env = dict(os.environ)
    env["PREVIEWGEN_RELEASE_GATE"] = "1"
    env.pop("PREVIEWGEN_BINARY", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/integration/test_release_renderers_gate.py::test_release_frozen_artifact_is_exercised_when_supplied",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode != 0, "release gate must fail when no frozen artifact is supplied"
    assert "PREVIEWGEN_BINARY must be set" in (completed.stdout + completed.stderr)
