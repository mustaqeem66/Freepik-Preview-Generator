#!/usr/bin/env python3
"""Check that a packaged native WebView rendered meaningful React DOM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", type=Path, required=True, help="the render-evidence marker file")
    args = parser.parse_args(argv)

    marker = args.marker
    if not marker.is_file():
        print(f"No render-evidence marker at {marker}.", file=sys.stderr)
        return 2
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"Could not read render-evidence marker {marker}: {exc}", file=sys.stderr)
        return 2
    if not raw:
        print(f"Render-evidence marker {marker} is empty.", file=sys.stderr)
        return 2
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Render-evidence marker {marker} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(result, dict):
        print(f"Render-evidence marker {marker} is not a JSON object.", file=sys.stderr)
        return 2

    try:
        child_count = int(result.get("rootChildCount", 0))
        width = float(result.get("rootWidth", 0))
        height = float(result.get("rootHeight", 0))
        text_length = int(result.get("textLength", 0))
    except (TypeError, ValueError):
        print(f"Render-evidence marker contains invalid measurements: {result!r}", file=sys.stderr)
        return 1

    if (
        result.get("ok") is True
        and result.get("error") is None
        and child_count > 0
        and width > 0
        and height > 0
        and text_length > 0
    ):
        print(
            "Packaged render evidence passed: "
            f"root children={child_count}, size={width:g}x{height:g}, text={text_length}."
        )
        return 0

    print(f"Packaged render evidence failed: {result!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
