"""Regression tests for opt-in, best-effort desktop notifications."""
from __future__ import annotations

import json
import re
import subprocess
import threading
from types import SimpleNamespace

import pytest

from previewgen import notifications
from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


def test_notification_command_reports_nonzero_status(monkeypatch):
    monkeypatch.setattr(notifications.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=7))
    assert notifications._run_hidden(["notify-send", "x"]) is False


def test_notification_command_reports_missing_stack_and_timeout(monkeypatch):
    def no_service(*_args, **_kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(notifications.subprocess, "run", no_service)
    assert notifications._run_hidden(["notify-send"]) is False

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("notify-send", timeout=6)

    monkeypatch.setattr(notifications.subprocess, "run", timed_out)
    assert notifications._run_hidden(["notify-send"]) is False


def test_windows_notification_escapes_apostrophes(monkeypatch):
    commands = []
    monkeypatch.setattr(notifications.sys, "platform", "win32")
    monkeypatch.setattr(
        notifications.subprocess, "run",
        lambda cmd, **kwargs: commands.append((cmd, kwargs)) or SimpleNamespace(returncode=0),
    )
    assert notifications.notify("a'b", "test'; Write-Host unexpected") is True
    cmd, kwargs = commands[0]
    assert cmd[:2] == ["powershell.exe", "-NoProfile"]
    assert "'a''b'" in cmd[-1]
    assert "'test''; Write-Host unexpected'" in cmd[-1]
    assert kwargs["timeout"] == 6.0
    assert "PreviewGen.Studio" in cmd[-1]


def test_linux_and_macos_notification_commands(monkeypatch):
    commands = []
    monkeypatch.setattr(
        notifications.subprocess, "run",
        lambda cmd, **kwargs: commands.append(cmd) or SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(notifications.sys, "platform", "linux")
    assert notifications.notify("t", "m")
    assert commands[-1][:2] == ["notify-send", "--app-name"]
    monkeypatch.setattr(notifications.sys, "platform", "darwin")
    assert notifications.notify("a\"b", "hello")
    assert 'a\\"b' in commands[-1][-1]


def test_batch_summary_status():
    assert notifications.batch_summary_text({"success": 2}) == "Batch complete: 2 saved"
    assert notifications.batch_summary_text({"cancelled": True, "success": 1}).startswith("Batch cancelled:")
    assert notifications.batch_summary_text({"status": "failed", "failed": 2}).startswith("Batch failed:")
    assert notifications.batch_summary_text({"status": "completed_with_warnings", "truncated": True}).startswith(
        "Batch completed with warnings:"
    )


def test_notifications_are_opt_in_and_keep_the_batch_operation_id(monkeypatch):
    api = DesktopApi()
    scripts = []
    api._window = SimpleNamespace(evaluate_js=scripts.append)
    delivered = []
    done = threading.Event()

    def record(summary):
        delivered.append(summary)
        done.set()
        return True

    monkeypatch.setattr(notifications, "notify_batch_finished", record)
    api._on_batch_finished({"success": 2, "files": [{"path": "not sent"}]}, "op1")
    assert not delivered
    api._on_batch_finished({"success": 3, "files": [{"path": "not sent"}]}, "op2", notify_enabled=True)
    assert done.wait(3)
    assert delivered and "files" not in delivered[0]
    first = json.loads(re.search(r"window\.__onBridgeEvent\((\{.*\})\)", scripts[0]).group(1))
    second = json.loads(re.search(r"window\.__onBridgeEvent\((\{.*\})\)", scripts[1]).group(1))
    assert first["operationId"] == "op1"
    assert second["operationId"] == "op2"
    assert "files" not in second["payload"]
