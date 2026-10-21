"""Regression checks for operation-specific scan cancellation."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from previewgen.api import DesktopApi
from previewgen.scanner import ScanContext, ScannerService

pytestmark = pytest.mark.core


def test_cancel_old_scan_does_not_stop_current_context(tmp_path: Path) -> None:
    scanner = ScannerService()
    active = ScanContext(
        scan_id="scan-new",
        root=tmp_path,
        cancel_event=threading.Event(),
        temp_root=tmp_path,
    )
    scanner.active_scan_context = active

    assert scanner.cancel_scan("scan-old") is False
    assert not active.cancel_event.is_set()

    assert scanner.cancel_scan("scan-new") is True
    assert active.cancel_event.is_set()


def test_cancel_without_current_context_is_noop() -> None:
    scanner = ScannerService()
    assert scanner.cancel_scan("missing") is False
    assert scanner.cancel_scan() is False


def test_desktop_bridge_returns_scoped_cancellation_result(tmp_path: Path) -> None:
    api = DesktopApi()
    isolated = ScannerService()
    isolated.active_scan_context = ScanContext(
        scan_id="current",
        root=tmp_path,
        cancel_event=threading.Event(),
        temp_root=tmp_path,
    )
    api.scanner = isolated
    assert api.cancel_scan("old") == {"ok": True, "cancelled": False}
    assert not isolated.active_scan_context.cancel_event.is_set()
    assert api.cancel_scan("current") == {"ok": True, "cancelled": True}
    assert isolated.active_scan_context.cancel_event.is_set()
    api.cleanup()
