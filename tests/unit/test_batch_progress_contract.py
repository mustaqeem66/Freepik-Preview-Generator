"""Progress callback contract and overhead (P2-9)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch.runner import _progress_reporter  # noqa: E402

pytestmark = pytest.mark.core


def test_four_argument_callback_receives_monotonic_sequence_numbers():
    events: list[tuple[int, int, str, int]] = []

    report = _progress_reporter(lambda cur, tot, msg, seq: events.append((cur, tot, msg, seq)))
    report(0, -1, "discovering")
    report(1, 2, "one")
    report(2, 2, "two")

    assert events == [(0, -1, "discovering", 1), (1, 2, "one", 2), (2, 2, "two", 3)]


def test_three_argument_callback_still_supported():
    events: list[tuple[int, int, str]] = []

    report = _progress_reporter(lambda cur, tot, msg: events.append((cur, tot, msg)))
    report(1, 4, "one")

    assert events == [(1, 4, "one")]


def test_signature_is_inspected_once_per_batch(monkeypatch):
    import previewgen.batch.runner as runner

    calls = 0
    original = runner.inspect.signature

    def counting_signature(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.inspect, "signature", counting_signature)
    report = _progress_reporter(lambda cur, tot, msg: None)
    for _ in range(500):
        report(1, 2, "x")

    assert calls == 1
