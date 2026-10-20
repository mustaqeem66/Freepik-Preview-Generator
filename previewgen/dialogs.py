"""GUI-independent dialog and script helpers.

Kept separate from :mod:`previewgen.desktop_runtime` so the AppleScript
literal encoding can be imported and tested without ``webview``.
"""
from __future__ import annotations


def applescript_string(text: str) -> str:
    """Quote ``text`` as an AppleScript string literal.

    Backslashes and double quotes are escaped, and CR/LF are collapsed so the
    value can never terminate the literal and inject further AppleScript.
    """
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped.replace("\r", " ").replace("\n", " ") + '"'
