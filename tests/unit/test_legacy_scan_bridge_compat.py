"""Hotfix: a backend upgrade must not blank old WebView asset lists."""
from __future__ import annotations

import json

import pytest

from previewgen.api import DesktopApi
from previewgen.scanner import ScannerService

pytestmark = pytest.mark.core


class Window:
    def __init__(self):
        self.scripts = []

    def evaluate_js(self, script):
        self.scripts.append(script)


def _completed(window):
    token = "window.__onBridgeEvent("
    script = window.scripts[-1]
    assert token in script
    return json.loads(script.split(token, 1)[1][:-1])["payload"]["result"]


def test_existing_frontend_gets_full_scan_without_paging_opt_in():
    api = DesktopApi()
    api.scanner = ScannerService()
    api._window = Window()
    rows = [{"name": str(i), "path": f"/root/{i}.png", "ext": "PNG",
             "is_3d": False} for i in range(200)]
    try:
        assert api._scan_paging_enabled is False
        api._on_scan_finished("legacy", {"files": rows, "total": 200})
        payload = _completed(api._window)
        assert payload["files"] == rows
        assert "paged" not in payload
    finally:
        api.cleanup()


def test_new_frontend_can_explicitly_request_paged_result(monkeypatch):
    api = DesktopApi()
    api.scanner = ScannerService()
    api._window = Window()
    monkeypatch.setattr(api.scanner, "start_scan", lambda folder: {"ok": True, "scanId": "new"})
    rows = [{"name": str(i), "path": f"/root/{i}.png", "ext": "PNG",
             "is_3d": False} for i in range(200)]
    try:
        api._add_authorized_input_folder("/root")
        assert api.start_scan("/root", paged=True)["ok"] is True
        assert api._scan_paging_enabled is True
        api._on_scan_finished("new", {"files": rows, "total": 200})
        payload = _completed(api._window)
        assert payload["files"] == []
        assert payload["paged"]["total"] == 200
        assert api.get_scan_page("new", 0)["value"]["nextOffset"] > 0
    finally:
        api.cleanup()
