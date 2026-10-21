"""Large folder scans must not inject thousands of source paths into one JS call."""
from __future__ import annotations

import json

import pytest

from previewgen.api import (
    SCAN_INLINE_RESULT_LIMIT,
    SCAN_PAGE_MAX_BYTES,
    SCAN_PAGE_MAX_ITEMS,
    DesktopApi,
)
from previewgen.scanner import ScannerService

pytestmark = pytest.mark.core


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def evaluate_js(self, script: str) -> None:
        self.scripts.append(script)


def _last_event(window: FakeWindow) -> dict:
    prefix = "window.__onBridgeEvent("
    script = window.scripts[-1]
    assert prefix in script and script.endswith(")")
    return json.loads(script.split(prefix, 1)[1][:-1])


def _row(index: int, padding: int = 0) -> dict:
    return {
        "name": f"{index}.png",
        "path": f"/source/{index}-" + ("a" * padding) + ".png",
        "ext": "PNG",
        "is_3d": False,
    }


def test_large_scan_completion_is_metadata_only_and_pages_stay_bounded() -> None:
    api = DesktopApi()
    api.scanner = ScannerService()
    api._scan_paging_enabled = True
    window = FakeWindow()
    api.window = window
    files = [_row(i, padding=450) for i in range(5000)]
    try:
        api._on_scan_finished("large-scan", {
            "files": files, "total": len(files), "status": "completed",
            "discovered": len(files), "truncated": False,
        })
        assert len(window.scripts) == 1
        assert len(window.scripts[0].encode("utf-8")) < 4096
        event = _last_event(window)
        assert event["event"] == "scan.finished"
        assert event["terminal"] is True
        assert event["payload"]["result"]["files"] == []
        assert event["payload"]["result"]["paged"] == {
            "total": 5000, "pageSize": SCAN_PAGE_MAX_ITEMS,
        }

        received: list[dict] = []
        offset = 0
        pages = 0
        while offset < len(files):
            result = api.get_scan_page("large-scan", offset, SCAN_PAGE_MAX_ITEMS)
            assert result["ok"], result
            page = result["value"]
            assert page["offset"] == offset
            assert page["scanId"] == "large-scan"
            assert page["nextOffset"] > offset
            assert page["total"] == 5000
            assert len(page["files"]) <= SCAN_PAGE_MAX_ITEMS
            assert len(json.dumps(page, ensure_ascii=False).encode("utf-8")) < SCAN_PAGE_MAX_BYTES
            received.extend(page["files"])
            offset = page["nextOffset"]
            pages += 1
        assert received == files
        assert pages > 5000 // SCAN_PAGE_MAX_ITEMS
        assert api._scan_page_state is None
        assert api.get_scan_page("large-scan", 0)["error"] == "SCAN_RESULT_EXPIRED"
        assert len(window.scripts) == 1
    finally:
        api.cleanup()


def test_small_scan_uses_legacy_terminal_envelope() -> None:
    api = DesktopApi()
    api.scanner = ScannerService()
    api._scan_paging_enabled = True
    window = FakeWindow()
    api.window = window
    original = [_row(i) for i in range(SCAN_INLINE_RESULT_LIMIT)]
    try:
        api._on_scan_finished("small-scan", {"files": original, "total": len(original)})
        delivered = _last_event(window)["payload"]["result"]
        assert delivered["files"] == original
        assert "paged" not in delivered
        assert api._scan_page_state is None
    finally:
        api.cleanup()


def test_byte_heavy_small_result_pages_and_oversized_row_fails_safely() -> None:
    api = DesktopApi()
    api.scanner = ScannerService()
    api._scan_paging_enabled = True
    api.window = FakeWindow()
    try:
        api._on_scan_finished("wide", {"files": [_row(1, padding=SCAN_PAGE_MAX_BYTES)], "total": 1})
        result = _last_event(api.window)["payload"]["result"]
        assert result["files"] == []
        assert result["paged"]["total"] == 1
        assert api.get_scan_page("wide", 0)["error"] == "SCAN_ROW_TOO_LARGE"
    finally:
        api.cleanup()


def test_scan_pages_are_sequential_and_revoked_when_new_scan_starts(monkeypatch) -> None:
    api = DesktopApi()
    api.scanner = ScannerService()
    api._scan_paging_enabled = True
    api.window = FakeWindow()
    try:
        api._on_scan_finished("old", {
            "files": [_row(i) for i in range(300)], "total": 300,
        })
        assert api.get_scan_page("other", 0)["error"] == "SCAN_RESULT_EXPIRED"
        assert api.get_scan_page("old", 128)["error"] == "SCAN_PAGE_OUT_OF_ORDER"
        assert api.get_scan_page("old", 0, 129)["error"] == "INVALID_SCAN_PAGE"
        assert api.get_scan_page("old", False)["error"] == "INVALID_SCAN_PAGE"
        first = api.get_scan_page("old", 0)
        assert first["ok"]
        assert first["value"]["nextOffset"] > 0
        assert api.get_scan_page("old", 0)["error"] == "SCAN_PAGE_OUT_OF_ORDER"

        monkeypatch.setattr(api.scanner, "start_scan", lambda folder: {"ok": True, "scanId": "new"})
        api.add_authorized_input_folder("/some/folder")
        assert api.start_scan("/some/folder") == {"ok": True, "scanId": "new"}
        assert api.get_scan_page("old", first["value"]["nextOffset"])["error"] == "SCAN_RESULT_EXPIRED"
    finally:
        api.cleanup()
