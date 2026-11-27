"""Bounded launcher for packaged desktop GUI smoke tests."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from scripts.run_gui_smoke import main

pytestmark = __import__("pytest").mark.core


def test_gui_smoke_returns_the_child_exit_code() -> None:
    code = main(["--timeout", "5", "--", sys.executable, "-c", "raise SystemExit(7)"])
    assert code == 7


def test_gui_smoke_captures_output(tmp_path) -> None:
    output = tmp_path / "gui.log"
    code = main(
        [
            "--timeout",
            "5",
            "--output",
            str(output),
            "--",
            sys.executable,
            "-c",
            "print('native output')",
        ]
    )

    assert code == 0
    assert "native output" in output.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group behavior")
def test_gui_smoke_kills_a_child_that_ignores_sigterm(tmp_path) -> None:
    child_pid_file = tmp_path / "descendant.pid"
    parent_code = (
        "import os, pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )

    code = main(
        [
            "--timeout",
            "0.5",
            "--",
            sys.executable,
            "-c",
            parent_code,
        ]
    )

    assert code == 124
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        state = subprocess.run(
            ["ps", "-o", "state=", "-p", str(child_pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
        if state.startswith("Z"):
            break
        time.sleep(0.05)
    else:
        os.kill(child_pid, signal.SIGKILL)
        raise AssertionError(f"GUI descendant {child_pid} survived forceful cleanup")


def test_gui_smoke_times_out_and_terminates_the_child(tmp_path) -> None:
    pid_file = tmp_path / "child.pid"
    child_code = (
        f"import os, pathlib, time; pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)"
    )
    code = main(
        [
            "--timeout",
            "0.2",
            "--",
            sys.executable,
            "-c",
            child_code,
        ]
    )
    assert code == 124
    pid = int(pid_file.read_text(encoding="utf-8"))
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert str(pid) not in result.stdout, f"timed-out GUI child {pid} is still alive"
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError(f"timed-out GUI child {pid} is still alive")
