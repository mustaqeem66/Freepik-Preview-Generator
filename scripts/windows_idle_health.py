"""Manual Windows GUI responsiveness probe for PreviewGen packaged builds.

Usage (from the repository root, with the actual PreviewGen window running):
    python scripts/windows_idle_health.py --pid 12345 --seconds 300 \
      --csv previewgen-idle-health.csv

No artwork or diagnostics are uploaded, and the target process is never
terminated, restarted, instrumented or modified. This is a *native* Windows
message-pump probe, not a replacement for a human reproducible hang report.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import datetime as dt
import logging
import sys
import time
from ctypes import wintypes
from pathlib import Path


class FailureGate:
    """Track sustained unresponsiveness separately from a missing window."""

    def __init__(self, threshold: int = 3) -> None:
        if threshold < 2:
            raise ValueError("Require at least two bad samples to reduce false positives")
        self.threshold = threshold
        self.failed = 0
        self.missing = 0
        self.had_hang = False
        self.had_missing = False

    def observe(self, state: bool | None) -> str:
        if state is True:
            self.failed = 0
            self.missing = 0
            return "responsive"
        if state is False:
            self.failed += 1
            self.missing = 0
            if self.failed >= self.threshold:
                self.had_hang = True
            return "unresponsive"
        self.missing += 1
        self.failed = 0
        if self.missing >= self.threshold:
            self.had_missing = True
        return "no-window"

    @property
    def passed(self) -> bool:
        return not self.had_hang and not self.had_missing


def probe_window_pid(pid: int, timeout_ms: int) -> tuple[bool | None, int]:
    """Find visible PreviewGen windows owned by PID, check their message pumps.

    The Win32 WM_NULL / SendMessageTimeoutW probe has a bounded timeout.
    A long native modal dialog or system load can trigger a false positive.
    """
    if sys.platform != "win32":
        raise RuntimeError("This probe only runs on Windows.")
    if pid <= 0:
        raise ValueError("Target PID must be positive.")

    user32 = ctypes.windll.user32
    handles: list[int] = []
    visitor_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visitor(hwnd: int, _lparam: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(wintypes.HWND(hwnd)):
            return True
        length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(wintypes.HWND(hwnd), title_buffer, length + 1)
        if "PreviewGen" in title_buffer.value:
            handles.append(hwnd)
        return True

    callback = visitor_type(visitor)
    if not user32.EnumWindows(callback, 0):
        raise OSError("Could not enumerate native Windows top-level windows.")

    if not handles:
        return None, 0

    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    for hwnd in handles:
        result = ctypes.c_size_t()
        # WM_NULL = 0; SMTO_ABORTIFHUNG = 0x0002.
        ok = user32.SendMessageTimeoutW(
            wintypes.HWND(hwnd), 0, 0, 0, 0x0002, timeout_ms, ctypes.byref(result)
        )
        if not ok:
            return False, len(handles)
    return True, len(handles)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="PID owning the real PreviewGen window")
    parser.add_argument("--seconds", type=int, default=300, help="How many seconds to monitor (default: 300)")
    parser.add_argument("--interval", type=float, default=3.0, help="Probe interval in seconds (default: 3)")
    parser.add_argument("--timeout-ms", type=int, default=750, help="Bound per native WM_NULL probe (default: 750)")
    parser.add_argument("--threshold", type=int, default=3, help="Consecutive failures before flagging (default: 3)")
    parser.add_argument("--csv", type=Path, default=Path("previewgen-idle-health.csv"),
                        help="CSV path containing only timestamps, PID and responsiveness signals")
    args = parser.parse_args(argv)
    if args.pid <= 0 or not 10 <= args.seconds <= 86_400:
        parser.error("PID must be positive and duration must be between 10 and 86400 seconds")
    if not 0.5 <= args.interval <= 60.0 or not 50 <= args.timeout_ms <= 5_000:
        parser.error("Interval must be 0.5–60 seconds and timeout 50–5000 milliseconds")
    if args.threshold < 2:
        parser.error("Threshold must be at least 2")
    return args


def run_monitor(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        print("ERROR: This probe must run on Windows, not under Linux/WSL/macOS.", file=sys.stderr)
        return 2
    gate = FailureGate(args.threshold)
    start = time.monotonic()
    deadline = start + args.seconds
    samples = 0
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["utc_timestamp", "pid", "result", "matching_windows"])
        while True:
            observed_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            try:
                responding, windows = probe_window_pid(args.pid, args.timeout_ms)
            except (OSError, RuntimeError, AttributeError, ValueError) as exc:
                logging.warning("Windows probe unavailable: %s", exc)
                responding, windows = None, 0

            state = gate.observe(responding)
            writer.writerow([observed_at, args.pid, state, windows])
            csvfile.flush()
            samples += 1
            if state != "responsive":
                print(f"{observed_at} {state} (matching windows={windows})")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(args.interval, remaining))
    label = "PASS" if gate.passed else "FAIL"
    print(f"{label}: {samples} native probe samples for PID {args.pid}; results: {args.csv}")
    if not gate.passed:
        print("Review the application's HANG DIAGNOSTIC logs; native modal dialogs, shutdown "
              "and system load can cause false positives. Do not treat this as root-cause proof.")
    return 0 if gate.passed else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_monitor(args)


if __name__ == "__main__":
    raise SystemExit(main())
