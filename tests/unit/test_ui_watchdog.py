"""The UI watchdog must diagnose (not terminate) Windows GUI hangs even when idle."""
from __future__ import annotations

import logging
import sys

import pytest

from previewgen.ui_watchdog import WindowHangDetector, log_thread_stacks, windows_window_responding

pytestmark = pytest.mark.core


def test_monitor_detects_idle_window_hang_without_backend_events():
    detector = WindowHangDetector(threshold=3, cooldown_seconds=60)
    assert not detector.observe(False, now=10)
    assert not detector.observe(False, now=13)
    assert detector.observe(False, now=16)
    assert not detector.observe(False, now=20)
    assert detector.observe(False, now=80)


def test_transient_os_dialog_or_minimized_window_does_not_trigger_false_alarm():
    detector = WindowHangDetector(threshold=3)
    assert not detector.observe(False, now=1)
    assert not detector.observe(False, now=2)
    assert not detector.observe(None, now=3)
    assert not detector.observe(False, now=4)
    assert not detector.observe(True, now=5)
    assert not detector.observe(False, now=6)
    assert not detector.observe(False, now=7)
    assert detector.observe(False, now=8)


def test_log_thread_stacks_has_diagnostic_marker(caplog):
    with caplog.at_level(logging.ERROR):
        log_thread_stacks("simulated stalled UI")
    assert "HANG DIAGNOSTIC: simulated stalled UI" in caplog.text
    assert "thread=" in caplog.text


def test_non_windows_probe_does_not_touch_win32_api(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert windows_window_responding() is None
