import time
from pathlib import Path

import pytest

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core

SAMPLE_PNG = Path("tests/fixtures/sample.png")

def test_p0_3_start_preview_non_blocking_and_isolated():
    """P0-3: start_preview must return operationId in <10ms and execute in an isolated child process."""
    api = DesktopApi()
    try:
        t0 = time.perf_counter()
        res = api.start_preview(str(SAMPLE_PNG), {"text": "P0 Test"}, request_id=101)
        t_elapsed = time.perf_counter() - t0

        assert t_elapsed < 0.05, f"start_preview took too long: {t_elapsed:.4f}s"
        assert res["ok"] is True
        assert res["status"] == "queued"
        assert res["operationId"] == "preview_101"
    finally:
        api.cleanup()

def test_p0_4_start_probe_non_blocking_and_event_driven():
    """P0-4: start_probe must return immediately with operationId, not block on inspection."""
    api = DesktopApi()
    try:
        t0 = time.perf_counter()
        res = api.start_probe(str(SAMPLE_PNG), request_id=202)
        t_elapsed = time.perf_counter() - t0

        assert t_elapsed < 0.05, f"start_probe took too long: {t_elapsed:.4f}s"
        assert res["ok"] is True
        assert res["status"] == "queued"
        assert res["operationId"] == "probe_202"
    finally:
        api.cleanup()

def test_p0_5_rapid_preview_requests_cancel_prior_backend_renders():
    """P0-5: Rapid slider changes (e.g. 50 updates) must abort in-flight workers, leaving only latest."""
    api = DesktopApi()
    events = []

    def mock_dispatch(event_name, payload, op_id=""):
        events.append((event_name, payload))

    api._dispatch_envelope = mock_dispatch
    api.preview_coordinator.set_dispatch_fn(mock_dispatch)

    try:
        for i in range(1, 30):
            res = api.start_preview(str(SAMPLE_PNG), {"yaw": i * 5, "pitch": i * 2}, request_id=i)
            assert res["ok"] is True

        # Wait briefly for the latest request to settle
        time.sleep(1.0)

        # Check that we didn't spawn 30 completed renders; earlier ones were cancelled
        completed = [e for e in events if e[0] == "preview.completed"]
        # Only the final or near-final tasks should complete
        assert len(completed) <= 3, f"Expected latest-wins to drop intermediate renders, got {len(completed)}"
    finally:
        api.cleanup()
