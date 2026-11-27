"""Bounded launcher for packaged desktop GUI smoke tests."""

from __future__ import annotations

import sys

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


def test_gui_smoke_times_out_and_terminates_the_child() -> None:
    code = main(
        [
            "--timeout",
            "0.2",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ]
    )
    assert code == 124
