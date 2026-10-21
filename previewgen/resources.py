"""
PreviewGen Resource Resolution
GUI-independent helpers for locating bundled resources (frontend bundle, assets).
No webview imports.
"""
from __future__ import annotations

import sys
from pathlib import Path


def get_resource_dir() -> Path:
    """Get the resource directory for bundled assets."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent


def get_html_dist() -> Path:
    """Find the built frontend HTML bundle."""
    if getattr(sys, "frozen", False):
        # A frozen executable must only use assets inside its own bundled
        # resource root. Never silently substitute a developer checkout.
        candidates = [get_resource_dir() / "frontend" / "dist" / "index.html"]
    else:
        # A source checkout's canonical Vite output wins over older, copied
        # previewgen/frontend/dist assets left behind by packaging scripts.
        candidates = [
            Path(__file__).parent.parent / "frontend" / "dist" / "index.html",
            Path(__file__).parent / "frontend" / "dist" / "index.html",
        ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]
