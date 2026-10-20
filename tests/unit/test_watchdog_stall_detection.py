"""Watchdog stall detection must only fire while work is in flight.

The heartbeat advances only when Python pushes a bridge event, so an idle
application is silent by definition. Treating that silence as a freeze made
the watchdog dump every thread stack every five seconds during normal use.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.core


class _StubWebview(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("webview")


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", _StubWebview())
    monkeypatch.delitem(sys.modules, "previewgen.desktop_runtime", raising=False)
    return importlib.import_module("previewgen.desktop_runtime")


class _Api:
    def __init__(self, heartbeat: float, busy: bool) -> None:
        self._last_heartbeat_time = heartbeat
        self._busy = busy

    def has_outstanding_work(self) -> bool:
        return self._busy


def test_idle_app_is_not_stalled(runtime):
    assert runtime.bridge_is_stalled(_Api(heartbeat=0.0, busy=False), now=1_000.0) is False
    assert runtime.bridge_is_stalled(_Api(heartbeat=10.0, busy=False), now=1_000.0) is False


def test_recent_activity_is_not_stalled(runtime):
    assert runtime.bridge_is_stalled(_Api(heartbeat=990.0, busy=True), now=1_000.0) is False


def test_quiet_bridge_with_work_in_flight_is_stalled(runtime):
    assert runtime.bridge_is_stalled(_Api(heartbeat=10.0, busy=True), now=1_000.0) is True


def test_idle_api_reports_no_outstanding_work():
    from previewgen.api import DesktopApi

    api = DesktopApi()
    assert api.has_outstanding_work() is False
    try:
        from previewgen.lifecycle import ActiveOperation

        op = ActiveOperation(operation_id="probe_test", kind="asset_probe")
        api.lifecycle.register_operation(op)
        assert api.has_outstanding_work() is True
        api.lifecycle.unregister_operation("probe_test")
        assert api.has_outstanding_work() is False
    finally:
        api.cleanup()
