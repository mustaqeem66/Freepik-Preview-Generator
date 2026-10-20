"""Startup cleanup must not make the desktop entrypoint wait for slow disks."""
from __future__ import annotations

import threading

import pytest

from previewgen.entrypoint import schedule_stale_temp_cleanup

pytestmark = pytest.mark.core


def test_slow_temp_sweep_is_not_on_the_desktop_startup_thread(monkeypatch):
    from previewgen import tempfiles

    entered = threading.Event()
    release = threading.Event()
    complete = threading.Event()

    def slow_cleanup():
        entered.set()
        release.wait(timeout=3)
        complete.set()

    monkeypatch.setattr(tempfiles, "cleanup_stale_temp_dirs", slow_cleanup)
    schedule_stale_temp_cleanup()
    assert entered.wait(1)
    assert not complete.is_set(), "Desktop must not wait for stale-temp deletion"
    release.set()
    assert complete.wait(1)


def test_open_diagnostics_folder_is_authorized_and_local(monkeypatch, tmp_path):
    from previewgen import settings
    from previewgen.api import DesktopApi

    logs = tmp_path / "local-logs"
    monkeypatch.setattr(settings, "get_log_directory", lambda: logs)
    api = DesktopApi()
    visited = []
    monkeypatch.setattr(
        api, "open_folder",
        lambda path: visited.append(path) or {"ok": True, "error": None},
    )
    result = api.open_diagnostics_folder()
    assert result["ok"]
    assert logs.is_dir()
    assert api.is_authorized_path(logs)
    assert visited == [str(logs)]
    api.cleanup()
