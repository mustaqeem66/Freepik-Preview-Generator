import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


class _FakeWindow:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def evaluate_js(self, script: str) -> None:
        self.calls.append(script)


def _extract_envelope(script: str) -> dict:
    match = re.search(r"window\.__onBridgeEvent\((\{.*\})\)", script)
    assert match, f"no typed envelope emitted in: {script}"
    return json.loads(match.group(1))


def test_envelope_carries_event_operation_id_and_monotonic_sequence():
    api = DesktopApi()
    api.window = _FakeWindow()

    api._on_scan_progress("scan-1", 3)
    api._on_scan_finished("scan-1", {"files": []})

    first = _extract_envelope(api.window.calls[0])
    second = _extract_envelope(api.window.calls[1])

    assert first["event"] == "scan.progress"
    assert first["operationId"] == "scan-1"
    assert first["payload"] == {"scanId": "scan-1", "count": 3}
    assert second["event"] == "scan.finished"
    assert second["operationId"] == "scan-1"
    assert second["sequence"] == first["sequence"] + 1
    assert first["terminal"] is False
    assert second["terminal"] is True


def test_batch_envelope_uses_batch_operation_id():
    api = DesktopApi()
    api.window = _FakeWindow()
    api._batch_operation_id = "batch-deadbeef"

    api._on_batch_finished({"success": 1, "failed": 0})

    env = _extract_envelope(api.window.calls[0])
    assert env["event"] == "batch.finished"
    assert env["operationId"] == "batch-deadbeef"
    assert env["payload"] == {"success": 1, "failed": 0}
    assert env["terminal"] is True


def test_only_terminal_events_flagged_terminal():
    api = DesktopApi()
    api.window = _FakeWindow()

    api._on_scan_progress("scan-1", 1)
    api._on_scan_finished("scan-1", {"files": []})
    api._on_batch_finished({"success": 0})

    flags = [_extract_envelope(call)["terminal"] for call in api.window.calls]
    assert flags == [False, True, True]
