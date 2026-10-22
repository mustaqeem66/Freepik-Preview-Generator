"""Desktop runtime launch behaviour (P0-1 regression).

The GUI auto-close watchdog exists only for ``--gui-smoke-test``. On a normal
launch it must never be armed, or the window destroys itself a few seconds
after opening. It also must not rely on ``os`` being imported inside the smoke
branch (that produced a ``NameError`` on ordinary launches).
"""
from __future__ import annotations

import importlib
import sys
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


def test_linux_smoke_without_webview_bindings_fails_closed(monkeypatch, tmp_path):
    """A Linux smoke test with no `gi` must not report a pass.

    The smoke mode exists to prove the native WebView stack works. Treating a
    missing GTK binding as "fulfil it headlessly and return 0" let the release
    gate certify a GUI that was never created, and wrote the readiness marker
    the CI step asserts on.
    """
    runtime, fake_webview, _fake_api = _load_runtime(
        monkeypatch, tmp_path, ["previewgen", "--gui-smoke-test"]
    )
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda _name: None, raising=True
    )

    marker = tmp_path / "ready.marker"
    monkeypatch.setenv("PREVIEWGEN_READY_MARKER", str(marker))

    assert runtime.start_desktop_app() == 1
    assert not marker.exists()
    assert fake_webview.started is False


def test_native_titlebar_env_fallback_disables_frameless(monkeypatch, tmp_path):
    runtime, fake_webview, fake_api = _load_runtime(
        monkeypatch, tmp_path, ["previewgen"]
    )
    monkeypatch.setenv("PREVIEWGEN_NATIVE_TITLEBAR", "1")
    assert runtime.start_desktop_app() == 0
    assert fake_webview.window_options["frameless"] is False
    assert fake_api.custom_chrome is False
