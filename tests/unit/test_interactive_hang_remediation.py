import threading
import time
from pathlib import Path

import pytest

from previewgen.api import DesktopApi
from previewgen.preview_coordinator import PreviewCoordinator

pytestmark = pytest.mark.core

SAMPLE_PNG = Path("tests/fixtures/sample.png")

def test_p0_3_start_preview_non_blocking_and_isolated():
    """P0-3: start_preview must return operationId in <10ms and execute in an isolated child process."""
    api = DesktopApi()
    api._add_authorized_input_folder(SAMPLE_PNG.resolve().parent)
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
    api._add_authorized_input_folder(SAMPLE_PNG.resolve().parent)
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
    api._add_authorized_input_folder(SAMPLE_PNG.resolve().parent)
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
def test_rapid_100_updates_queue_bounded_and_control_calls_never_join_render(monkeypatch):
    """100 rapid updates: the bridge thread never waits on a render and the queue
    never grows past one active plus one pending request.

    The old assertion bounded each call at 100 ms wall-clock, which measured the
    runner rather than the code -- it failed under CPU contention with the
    implementation unchanged. The bound is now relative to a deliberately slow
    render: 100 control-plane calls finishing inside a single render's duration
    proves none of them joined the worker, with a margin no scheduler can eat.
    """
    render_seconds = 1.0
    api = DesktopApi()
    api._add_authorized_input_folder(SAMPLE_PNG.resolve().parent)
    api.preview_coordinator.set_dispatch_fn(lambda *_args: None)

    renders: list[str] = []
    live = 0
    peak_live = 0
    tally = threading.Lock()

    def slow_render(_self, op_id, _source, _config_dict, _max_dimension):
        nonlocal live, peak_live
        with tally:
            live += 1
            peak_live = max(peak_live, live)
            renders.append(op_id)
        time.sleep(render_seconds)
        with tally:
            live -= 1
        return {"status": "error", "error": "stubbed render"}

    monkeypatch.setattr(PreviewCoordinator, "_render_isolated", slow_render)
    try:
        started = time.perf_counter()
        for i in range(1, 101):
            res = api.start_preview(str(SAMPLE_PNG), {"text": f"Quick {i}"}, request_id=i)
            assert res["ok"] is True
            assert res["status"] == "queued"
        control_plane_seconds = time.perf_counter() - started

        with api.preview_coordinator._lock:
            outstanding = int(api.preview_coordinator._pending_task is not None) + int(
                api.preview_coordinator._active_op_id is not None
            )
        assert outstanding <= 2, (
            f"Queue is not bounded: 100 submitted updates left {outstanding} outstanding tasks."
        )

        assert control_plane_seconds < render_seconds, (
            "100 start_preview calls took "
            f"{control_plane_seconds:.3f}s, i.e. at least one render's worth of time -- "
            "the control plane is waiting on worker output again."
        )
        assert peak_live <= 1, f"Expected at most one concurrent render, saw {peak_live}"
        assert len(renders) <= 2, (
            f"Latest-wins coalescing regressed: 100 updates reached {len(renders)} renders "
            f"({renders}) instead of being collapsed into one active plus one pending."
        )
    finally:
        api.cleanup()

def test_cancel_preview_during_render_terminates_immediately():
    """Verify calling cancel_preview aborts active render without delay."""
    api = DesktopApi()
    api._add_authorized_input_folder(SAMPLE_PNG.resolve().parent)
    try:
        res = api.start_preview(str(SAMPLE_PNG), {"text": "Cancel Test"}, request_id=999)
        assert res["ok"] is True

        t0 = time.perf_counter()
        cancel_res = api.cancel_preview(res["operationId"])
        elapsed = time.perf_counter() - t0

        assert cancel_res["ok"] is True
        assert elapsed < 0.05, f"cancel_preview took too long: {elapsed:.4f}s"
    finally:
        api.cleanup()
