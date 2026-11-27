#!/usr/bin/env python3
"""Run a packaged GUI smoke test with a timeout that also stops its children."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import sys

TIMEOUT_EXIT_CODE = 124


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    """Stop the smoke process and every native child it started."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a GUI smoke command is required")

    process = subprocess.Popen(command, start_new_session=True)
    try:
        return process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(
            f"FATAL: GUI smoke command exceeded {args.timeout:g}s; terminating its process group.",
            file=sys.stderr,
        )
        _terminate_group(process)
        return TIMEOUT_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
