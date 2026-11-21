#!/usr/bin/env python3
"""Check the packaged WebView CSP smoke verdict.

Pass only if the WebView rejected both benign script probes and decoded a
JPEG from the same loopback transport the Studio uses for previews.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--marker", type=Path, required=True, help="the CSP self-test marker file")
    args = parser.parse_args(argv)

    marker = args.marker
    if not marker.is_file():
        print(f"No CSP self-test marker at {marker}.", file=sys.stderr)
        return 2

    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"Could not read CSP self-test marker {marker}: {exc}", file=sys.stderr)
        return 2

    if not raw:
        print(f"CSP self-test marker {marker} is empty.", file=sys.stderr)
        return 2

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"CSP self-test marker {marker} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(result, dict):
        print(f"CSP self-test marker {marker} is not a JSON object.", file=sys.stderr)
        return 2

    expected = {
        "inlineScript": "blocked",
        "blobScript": "blocked",
        "previewJpeg": "loaded",
    }
    if all(result.get(key) == value for key, value in expected.items()) and "error" not in result:
        print("Packaged CSP smoke passed: inline/blob scripts blocked; loopback JPEG decoded.")
        return 0

    print(f"Packaged CSP smoke failed: {result!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
