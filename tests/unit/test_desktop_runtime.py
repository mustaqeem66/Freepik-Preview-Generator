"""Desktop runtime launch behaviour (P0-1 regression).

The GUI auto-close watchdog exists only for ``--gui-smoke-test``. On a normal
launch it must never be armed, or the window destroys itself a few seconds
after opening. It also must not rely on ``os`` being imported inside the smoke
branch (that produced a ``NameError`` on ordinary launches).
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.core


@pytest.fixture(autouse=True)
def _purge_runtime_module():
    """Never leak a runtime module bound to the stubbed webview into other tests."""
    yield
    sys.modules.pop("previewgen.desktop_runtime", None)


class _Signal:
    def __init__(self) -> None:
        self.callbacks: list[object] = []

    def __iadd__(self, callback: object):
        self.callbacks.append(callback)
        return self


class _Events:
    def __init__(self) -> None:
        self.navigating = _Signal()


class _FakeWindow:
    def __init__(self) -> None:
        self.events = _Events()
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class _FakeWebview(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("webview")
        self.window = _FakeWindow()
        self.started = False
        self.window_options = {}

    def create_window(self, *_args, **kwargs) -> _FakeWindow:
        self.window_options = kwargs
        return self.window

    def start(self, **_kwargs) -> None:
        self.started = True


class _FakeApi:
    def __init__(self) -> None:
        self._last_heartbeat_time = 0.0
        self.window = None
        self.cleaned_up = False

    def _set_window(self, window, *, custom_chrome=False) -> None:
        self.window = window
        self.custom_chrome = custom_chrome

    def cleanup(self) -> None:
        self.cleaned_up = True


def _load_runtime(monkeypatch, tmp_path, argv):
    fake_webview = _FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.delitem(sys.modules, "previewgen.desktop_runtime", raising=False)
    monkeypatch.setattr(sys, "argv", argv)

    runtime = importlib.import_module("previewgen.desktop_runtime")

    html = tmp_path / "index.html"
    html.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(runtime, "get_html_dist", lambda: html)

    fake_api = _FakeApi()
    monkeypatch.setattr(runtime, "DesktopApi", lambda: fake_api)
    return runtime, fake_webview, fake_api


def test_normal_launch_does_not_arm_auto_close_watchdog(monkeypatch, tmp_path):
    runtime, fake_webview, fake_api = _load_runtime(monkeypatch, tmp_path, ["previewgen"])

    exit_calls: list[int] = []
    monkeypatch.setattr(runtime.os, "_exit", lambda code: exit_calls.append(code))

    # An existing ready marker makes the smoke watchdog act immediately, so a
    # regression would destroy the window within ~1s instead of after 15s.
    marker = tmp_path / "ready.marker"
    marker.write_text("READY\n", encoding="utf-8")
    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(marker))

    assert runtime.start_desktop_app() == 0
    time.sleep(1.3)

    assert fake_webview.started is True
    assert fake_webview.window_options["frameless"] is True
    assert fake_webview.window_options["easy_drag"] is False
    assert fake_api.custom_chrome is True
    assert fake_api.cleaned_up is True
    assert fake_webview.window.destroyed is False
    assert exit_calls == []


def test_smoke_watchdog_exits_zero_when_the_frontend_never_reports_ready(monkeypatch, tmp_path):
    """The packaged CI gates must assert the ready marker, not the exit code.

    Issue #19's packaged Windows build never finished bridge injection and never
    reported ready, yet the smoke watchdog still destroyed the window and called
    ``os._exit(0)``, so a gate that only checks the exit status passes it.
    """
    runtime, fake_webview, _api = _load_runtime(monkeypatch, tmp_path, ["previewgen", "--gui-smoke-test"])
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime, "SMOKE_READY_POLL_SECONDS", 0.001)
    marker = tmp_path / "never-written.marker"
    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(marker))

    exited = threading.Event()
    exit_codes: list[int] = []

    def _record_exit(code: int) -> None:
        exit_codes.append(code)
        exited.set()

    monkeypatch.setattr(runtime.os, "_exit", _record_exit)

    assert runtime.start_desktop_app() == 0
    assert exited.wait(5.0), "smoke watchdog never terminated the process"
    assert exit_codes == [0]
    assert fake_webview.window.destroyed is True
    assert not marker.exists()


def test_smoke_watchdog_waits_for_the_csp_probe_after_the_frontend_is_ready(monkeypatch, tmp_path):
    """The CSP probe must get its own budget, starting when the frontend is ready.

    The packaged macOS gate once failed with no CSP marker even though the
    frontend had mounted: the watchdog's single budget was spent from process
    start, so a slow frontend mount left too little time for the probe, and
    the watchdog destroyed the window while the probe was still running. The
    probe's wait must therefore start when the frontend reports ready, and
    the window must survive until the marker is written.
    """
    runtime, fake_webview, _api = _load_runtime(monkeypatch, tmp_path, ["previewgen", "--gui-smoke-test"])
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    # A ready budget of two polls: the frontend is seen on the second poll,
    # which leaves no budget in the old single-budget scheme for a probe that
    # finishes afterwards.
    monkeypatch.setattr(runtime, "SMOKE_READY_POLL_ATTEMPTS", 2)
    monkeypatch.setattr(runtime, "SMOKE_READY_POLL_SECONDS", 0.05)
    monkeypatch.setattr(runtime, "SMOKE_CSP_POLL_SECONDS", 0.01)
    # Keep the probe budget bounded by the test's 5-second deadline rather
    # than by a 150 ms wall-clock race between two scheduler threads. The CSP
    # writer still runs after the ready budget is exhausted, which is the
    # behavior this regression test protects.
    monkeypatch.setattr(runtime, "SMOKE_CSP_POLL_ATTEMPTS", 100000)

    ready_marker = tmp_path / "ready.marker"
    csp_marker = tmp_path / "csp_selftest.json"
    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(ready_marker))
    monkeypatch.setenv("PREVIEWGEN_CSP_MARKER", str(csp_marker))

    exited = threading.Event()
    monkeypatch.setattr(runtime.os, "_exit", lambda _code: exited.set())

    assert runtime.start_desktop_app() == 0

    # The frontend reports ready on the second poll of the ready budget.
    def _report_ready() -> None:
        time.sleep(0.02)
        ready_marker.write_text("READY\n", encoding="utf-8")

    threading.Thread(target=_report_ready, daemon=True).start()

    # The probe finishes after the ready budget would have been exhausted.
    # A real probe runs inside the live WebView, so it can only produce a
    # verdict while the window is still alive.
    def _write_csp_late() -> None:
        time.sleep(0.15)
        if not fake_webview.window.destroyed:
            csp_marker.write_text("{}", encoding="utf-8")

    threading.Thread(target=_write_csp_late, daemon=True).start()

    assert exited.wait(5.0), "smoke watchdog never terminated the process"
    assert fake_webview.window.destroyed is True
    assert csp_marker.exists(), "the window was destroyed before the CSP verdict"


def test_smoke_watchdog_does_not_wait_for_the_csp_probe_when_never_ready(monkeypatch, tmp_path):
    """A frontend that never mounts must not extend the smoke run.

    The CSP probe only starts once the frontend reports ready, so a frontend
    that never mounts has no probe to wait for. The watchdog must close the
    window on the ready budget alone rather than adding the CSP budget on
    top of it.
    """
    runtime, fake_webview, _api = _load_runtime(monkeypatch, tmp_path, ["previewgen", "--gui-smoke-test"])
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setattr(runtime, "SMOKE_READY_POLL_SECONDS", 0.001)
    monkeypatch.setattr(runtime, "SMOKE_CSP_POLL_SECONDS", 0.001)
    monkeypatch.setattr(runtime, "SMOKE_CSP_POLL_ATTEMPTS", 100000)

    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(tmp_path / "never.marker"))
    monkeypatch.setenv("PREVIEWGEN_CSP_MARKER", str(tmp_path / "csp.json"))

    exited = threading.Event()
    monkeypatch.setattr(runtime.os, "_exit", lambda _code: exited.set())

    assert runtime.start_desktop_app() == 0
    assert exited.wait(5.0), "smoke watchdog never terminated the process"
    assert fake_webview.window.destroyed is True


def test_linux_smoke_without_webview_bindings_fails_closed(monkeypatch, tmp_path):
    """A Linux smoke test with no `gi` must not report a pass.

    The smoke mode exists to prove the native WebView stack works. Treating a
    missing GTK binding as "fulfil it headlessly and return 0" let the release
    gate certify a GUI that was never created, and wrote the readiness marker
    the CI step asserts on.
    """
    runtime, fake_webview, _fake_api = _load_runtime(monkeypatch, tmp_path, ["previewgen", "--gui-smoke-test"])
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None, raising=True)

    marker = tmp_path / "ready.marker"
    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(marker))

    assert runtime.start_desktop_app() == 1
    assert not marker.exists()
    assert fake_webview.started is False


def test_native_titlebar_env_fallback_disables_frameless(monkeypatch, tmp_path):
    runtime, fake_webview, fake_api = _load_runtime(monkeypatch, tmp_path, ["previewgen"])
    monkeypatch.setenv("PREVIEWGEN_NATIVE_TITLEBAR", "1")
    assert runtime.start_desktop_app() == 0
    assert fake_webview.window_options["frameless"] is False
    assert fake_api.custom_chrome is False


def test_frozen_linux_missing_injected_bundle_fails_before_window_creation(monkeypatch, tmp_path):
    runtime, fake_webview, _api = _load_runtime(monkeypatch, tmp_path, ["previewgen"])
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime, "get_resource_dir", lambda: resource_dir, raising=False)

    assert runtime.start_desktop_app() == 1
    assert fake_webview.started is False
    assert fake_webview.window_options == {}
