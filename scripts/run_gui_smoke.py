#!/usr/bin/env python3
"""Run a packaged GUI smoke test with a timeout that also stops its children."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path

TIMEOUT_EXIT_CODE = 124


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    """Stop the smoke process and every native child it started."""
    if sys.platform == "win32":
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        return
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
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a GUI smoke command is required")

    output_handle = None
    output_stream = None
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output_handle = args.output.open("w", encoding="utf-8", errors="replace")
        output_stream = output_handle

    try:
        process = subprocess.Popen(
            command,
            start_new_session=True,
            stdout=output_stream,
            stderr=subprocess.STDOUT if output_stream is not None else None,
        )
        try:
            return process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            message = f"FATAL: GUI smoke command exceeded {args.timeout:g}s; terminating its process group."
            print(message, file=sys.stderr)
            if output_stream is not None:
                print(message, file=output_stream)
                output_stream.flush()
            _terminate_group(process)
            return TIMEOUT_EXIT_CODE
    finally:
        if output_handle is not None:
            output_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
