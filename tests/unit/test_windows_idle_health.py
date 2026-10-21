"""Portable unit tests for the native Windows idle-probe decision logic.

These tests do not use native Win32 APIs; a Windows GUI run is still required.
"""
from __future__ import annotations

import pytest

from scripts.windows_idle_health import FailureGate, parse_args

pytestmark = pytest.mark.core


def test_requires_sustained_failure_not_one_slow_sample() -> None:
    gate = FailureGate(threshold=3)
    assert [gate.observe(state) for state in (False, False, True, False, False)] == [
        "unresponsive", "unresponsive", "responsive", "unresponsive", "unresponsive"
    ]
    assert gate.passed is True
    gate.observe(False)
    assert gate.had_hang is True
    assert gate.passed is False


def test_absent_window_tracked_separately_from_unresponsive_window() -> None:
    gate = FailureGate(threshold=3)
    assert gate.observe(None) == "no-window"
    assert gate.observe(None) == "no-window"
    gate.observe(True)
    assert gate.passed is True
    for _ in range(3):
        gate.observe(None)
    assert gate.had_missing is True
    assert not gate.had_hang
    assert gate.passed is False


def test_cli_validates_duration_and_pid() -> None:
    args = parse_args(["--pid", "42", "--seconds", "15", "--interval", "1", "--threshold", "2"])
    assert args.pid == 42 and args.seconds == 15 and args.threshold == 2
    with pytest.raises(SystemExit):
        parse_args(["--pid", "-1"])
    with pytest.raises(SystemExit):
        parse_args(["--pid", "123", "--seconds", "2"])
    with pytest.raises(SystemExit):
        parse_args(["--pid", "123", "--threshold", "1"])
