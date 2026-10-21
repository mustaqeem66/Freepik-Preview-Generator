#!/usr/bin/env python3
"""Verify the compiled desktop UI contains the current Studio design contract.

This intentionally checks compiled assets, not TSX source. Running an older
PyInstaller executable still requires rebuilding/reinstalling that executable.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_CSS = (
    ".canvas-export-dock",
    ".precision-slider",
    ".library-scroll-content",
    ".inspector-scroll-content",
)
REQUIRED_JS = ("canvas-export-dock", "inspector-scroll-content")


def inspect_bundle(html: Path) -> list[str]:
    if not html.is_file():
        return [f"Compiled UI missing: {html} (run cd frontend && npm run build)"]
    folder = html.parent / "assets"
    styles = "\n".join(p.read_text("utf-8", errors="replace") for p in folder.glob("*.css"))
    scripts = "\n".join(p.read_text("utf-8", errors="replace") for p in folder.glob("*.js"))
    missing = [f"Compiled CSS missing {token}" for token in REQUIRED_CSS if token not in styles]
    missing.extend(f"Compiled JS missing {token}" for token in REQUIRED_JS if token not in scripts)
    return missing


def main() -> int:
    bundle = ROOT / "frontend" / "dist" / "index.html"
    missing = inspect_bundle(bundle)
    if missing:
        print("STALE/INCOMPLETE STUDIO BUNDLE:", file=sys.stderr)
        for item in missing:
            print(f" - {item}", file=sys.stderr)
        print("Rebuild the frontend, then rebuild/reinstall any frozen desktop binary.", file=sys.stderr)
        return 1
    print("Studio build contract OK (export dock, precision sliders, Lenis pane structure).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
