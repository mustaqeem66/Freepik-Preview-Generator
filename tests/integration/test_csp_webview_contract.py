"""Packaged-WebView CSP enforcement contract (issue #20).

The bundle test only proves the policy tag survives the build. This runs the real
WebKitGTK engine against the built artifact and fails if any directive is not
actually enforced. It is skipped on machines without a display or the native
WebKit bindings, so headless CI records a skip rather than a false pass.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "verify_csp_webview.py"
DIST = ROOT / "frontend" / "dist" / "index.html"

try:
    import gi

    gi.require_version("WebKit2", "4.1")
    from gi.repository import WebKit2  # noqa: F401
except (ImportError, ValueError):
    pytest.skip("native WebKit bindings not installed", allow_module_level=True)

has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@pytest.mark.skipif(not has_display, reason="no X11/Wayland display available")
@pytest.mark.skipif(not DIST.is_file(), reason="run npm run build in frontend/ first")
@pytest.mark.full_runtime
def test_production_csp_is_enforced_by_webkit(tmp_path):
    report = tmp_path / "csp-webview.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--report", str(report)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence = json.loads(report.read_text(encoding="utf-8"))
    assert evidence["results"], "no probes reported"
    assert all(row["passed"] for row in evidence["results"]), evidence["results"]
    # A run where nothing was permitted at all would pass by accident; the
    # controls prove the page was live and the policy did the filtering.
    assert [r for r in evidence["results"] if r["expected"] == "allowed"]
    assert any("Refused to" in line for line in evidence["engineReports"])
