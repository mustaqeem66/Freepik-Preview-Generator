#!/usr/bin/env python3
"""Audit every pinned Python package in a universal lock, on every platform.

pip-audit evaluates PEP 508 environment markers against the machine it runs on,
so a lock that pins Windows- and macOS-only packages (``clr-loader``,
``pythonnet``, the ``pyobjc`` frameworks, ...) is only partially audited on a
Linux CI runner: every pin whose marker does not match is skipped silently.

This script rewrites the platform markers in a committed lock so that every
pin in the file is evaluated, and audits the result with pip-audit. The
projection is a throwaway audit artifact, never a replacement lock: it is not
hash-pinned for installation and is never committed.

Usage:
    python scripts/audit_lock_all_platforms.py requirements-lock.txt
    python scripts/audit_lock_all_platforms.py requirements-lock.txt --project-out /tmp/lock.txt
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Markers that select an operating system. Rewriting the comparison target to
# an expression that is true on every platform keeps the marker syntactically
# valid while making the pin visible to the auditor.
PLATFORM_MARKERS = (
    "sys_platform",
    "platform_system",
    "os_name",
)

# A marker expression that is always true regardless of the host.
ALWAYS_TRUE = "python_version >= '3.0'"

# Every PEP 508 marker operator that can gate a pin by platform.
MARKER_PATTERN = re.compile(r"\b(" + "|".join(PLATFORM_MARKERS) + r")\s*(==|!=)\s*'([^']*)'")


def neutralize_markers(text: str) -> str:
    """Make platform-gated pins evaluate on any host.

    Only the platform comparisons are touched; version and interpreter
    markers are left alone so that a genuinely version-specific pin still
    describes what it selects.
    """
    return MARKER_PATTERN.sub(ALWAYS_TRUE, text)


def audit(lock: Path, python: str) -> int:
    """Audit every pin in `lock`, regardless of the host platform."""
    projected = neutralize_markers(lock.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="previewgen-audit-") as directory:
        target = Path(directory) / f"{lock.name}.all-platforms.txt"
        target.write_text(projected, encoding="utf-8")
        # --disable-pip reads the pins straight out of the lock instead of
        # building a virtualenv and installing them, which would require
        # system headers that CI runners do not have (e.g. libgirepository).
        return subprocess.run(
            [python, "-m", "pip_audit", "--require-hashes", "--disable-pip", "-r", str(target)],
            check=False,
        ).returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "lock",
        type=Path,
        nargs="+",
        help="one or more committed Python locks to audit",
    )
    parser.add_argument("--python", default=sys.executable, help="Python interpreter that has pip-audit installed")
    parser.add_argument(
        "--project-out",
        type=Path,
        default=None,
        help="also write the platform-neutral projection to this path (for inspection); "
        "only valid when auditing a single lock",
    )
    args = parser.parse_args(argv[1:])

    missing = [lock for lock in args.lock if not lock.is_file()]
    if missing:
        for lock in missing:
            print(f"error: lock file not found: {lock}", file=sys.stderr)
        return 2

    if args.project_out is not None:
        if len(args.lock) != 1:
            print("error: --project-out requires exactly one lock", file=sys.stderr)
            return 2
        if args.project_out.exists():
            print(
                f"error: refusing to overwrite existing file: {args.project_out}",
                file=sys.stderr,
            )
            return 2
        args.project_out.parent.mkdir(parents=True, exist_ok=True)
        args.project_out.write_text(neutralize_markers(args.lock[0].read_text(encoding="utf-8")), encoding="utf-8")
        print(f"wrote platform-neutral projection to {args.project_out}")

    # Audit every requested lock and report the first failure. Each lock is
    # audited independently so one bad lock does not hide the others.
    for lock in args.lock:
        print(f"auditing {lock}", flush=True)
        code = audit(lock, args.python)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
