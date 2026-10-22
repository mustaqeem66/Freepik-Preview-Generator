"""Bounded window chrome bridge contract without constructing a real GUI."""
from __future__ import annotations

from previewgen.api import DesktopApi


class Window:
    def __init__(self):
        self.actions = []

    def minimize(self):
        self.actions.append("minimize")

    def toggle_fullscreen(self):
        self.actions.append("fullscreen")

    def destroy(self):
        self.actions.append("close")


def test_rejects_unauthorized_window_actions():
    api = DesktopApi.__new__(DesktopApi)
    api._window = Window()
    api._custom_chrome_enabled = False
    assert api.window_action("close")["error"] == "NATIVE_CHROME_UNAVAILABLE"
    assert api._window.actions == []


def test_only_explicit_minimize_fullscreen_and_close_allowed(monkeypatch):
    api = DesktopApi.__new__(DesktopApi)
    api._window = Window()
    api._custom_chrome_enabled = True
    assert api.window_action("__class__")["error"] == "INVALID_WINDOW_ACTION"
    assert api.window_action("minimize")["ok"] is True
    assert api.window_action("fullscreen")["ok"] is True

    class Timer:
        def __init__(self, delay, fn):
            assert delay > 0
            self.fn = fn

        def start(self):
            self.fn()

    monkeypatch.setattr("previewgen.api.threading.Timer", Timer)
    assert api.window_action("close")["ok"] is True
    assert api._window.actions == ["minimize", "fullscreen", "close"]


def test_platform_metadata_tracks_native_fallback(monkeypatch):
    api = DesktopApi.__new__(DesktopApi)
    api._window = Window()
    api._custom_chrome_enabled = True
    monkeypatch.setattr("previewgen.api.sys.platform", "darwin")
    assert api.get_window_chrome()["value"] == {"enabled": True, "platform": "macos"}
    api._custom_chrome_enabled = False
    assert api.get_window_chrome()["value"] == {"enabled": False, "platform": "macos"}
