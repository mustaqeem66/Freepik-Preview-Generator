"""Tests for the packaged WebView CSP smoke probe.

The probe runs inside the live packaged WebView. It must prove two things at
once: the shipped policy refuses scripts, and the WebView can still load a
JPEG from PreviewGen's own loopback transport. A probe that only observes a
failure proves nothing, because an unreachable server fails the same way.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from previewgen.api import DesktopApi


@pytest.fixture
def api() -> DesktopApi:
    return DesktopApi()


class _Window:
    """A window that reports a scripted WebView verdict."""

    def __init__(self, verdict: dict[str, str] | None = None, error: Exception | None = None):
        self.verdict = verdict
        self.error = error
        self.scripts: list[str] = []

    def evaluate_js(self, script: str):
        self.scripts.append(script)
        if self.error is not None:
            raise self.error
        if "JSON.stringify(window.__pgCsp)" in script:
            return json.dumps(self.verdict or {})
        return "started"


def test_the_probe_requires_a_window(api):
    api._window = None

    assert api._probe_packaged_csp() == {"error": "NO_WINDOW"}


def test_a_blocked_policy_with_a_decoded_preview_passes(api):
    api._window = _Window({"inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "loaded"})

    outcome = api._probe_packaged_csp()

    assert outcome == {
        "inlineScript": "blocked",
        "blobScript": "blocked",
        "previewJpeg": "loaded",
    }


def test_an_executed_script_fails_the_probe(api):
    api._window = _Window({"inlineScript": "executed", "blobScript": "blocked", "previewJpeg": "loaded"})

    outcome = api._probe_packaged_csp()

    assert outcome["inlineScript"] == "executed"


def test_a_failed_preview_control_is_reported(api):
    """The policy result is meaningless without a working preview transport."""
    api._window = _Window({"inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "error"})

    outcome = api._probe_packaged_csp()

    assert outcome["previewJpeg"] == "error"


def test_an_unfinished_probe_is_reported_as_pending(api):
    api._window = _Window({"inlineScript": "blocked", "blobScript": "pending", "previewJpeg": "loaded"})

    outcome = api._probe_packaged_csp()

    assert outcome["blobScript"] == "pending"


def test_the_probe_publishes_the_preview_on_the_loopback_transport(api):
    window = _Window({"inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "loaded"})
    api._window = window

    api._probe_packaged_csp()

    probe = window.scripts[0]
    assert "http://127.0.0.1:" in probe
    assert "preview" in probe


def test_the_probe_releases_the_published_preview(api):
    window = _Window({"inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "loaded"})
    api._window = window

    api._probe_packaged_csp()

    assert api.preview_server.release_jpeg("preview_000000.jpg") is False


def test_a_broken_webview_fails_closed(api):
    api._window = _Window(error=RuntimeError("the WebView is gone"))

    with pytest.raises(RuntimeError):
        api._probe_packaged_csp()


def test_a_webview_that_never_answers_fails_closed_without_hanging(api):
    """A WebView that never answers must not hang the smoke gate forever.

    The pywebview backends block on a semaphore that is never released once
    the window's main loop has stopped, so a probe that called `evaluate_js`
    directly could hang for the lifetime of the process and the verdict would
    never be written. The call has to be bounded, and a timeout has to
    produce a verdict that fails the gate rather than silence.
    """
    api._window = _Window(verdict=None)
    released = threading.Event()

    def _never_returns(_script: str):
        released.wait(30)
        return "too late"

    api._window.evaluate_js = _never_returns  # type: ignore[method-assign]
    # Keep the test fast: the bound is what matters, not its exact value.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(api, "_probe_evaluation_timeout", 0.05, raising=False)
    try:
        started = time.monotonic()
        outcome = api._probe_packaged_csp()
        elapsed = time.monotonic() - started
    finally:
        monkeypatch.undo()
        released.set()

    assert "error" in outcome, f"a timed-out probe must report an error: {outcome!r}"
    # The probe must give up on its own. Without the bound it waits for the
    # WebView to answer and the gate hangs for the lifetime of the process.
    assert elapsed < 5.0, f"the probe waited {elapsed:.1f}s; the bound was not applied"


def test_the_probe_reports_an_unreadable_verdict_instead_of_raising(api):
    """A WebView that answers with something that is not the verdict fails closed."""
    api._window = _Window(verdict=None)

    def _returns_garbage(_script: str):
        return "not json"

    api._window.evaluate_js = _returns_garbage  # type: ignore[method-assign]

    outcome = api._probe_packaged_csp()

    assert "error" in outcome, f"an unreadable verdict must report an error: {outcome!r}"
