"""Packaged-WebView CSP enforcement contract (issue #20).

The bundle test only proves the policy tag survives the build. This runs the
real WebKitGTK engine against the built artifact and a copy with a relaxed
directive.

The test owns its display. An inherited Wayland session and an Xvfb session
can render the same page differently, so the probe must not depend on the
ambient desktop it happens to run under.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
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


def _xvfb_available() -> bool:
    return shutil.which("Xvfb") is not None and shutil.which("xdpyinfo") is not None


class _XvfbDisplay:
    """A private X display for the probe.

    ``xvfb-run`` cleans up its temporary directory after the child exits, and
    that cleanup fails under WSL, which masks the probe's own exit code. The
    test therefore owns the server process directly, on a display number that
    is free right now.
    """

    def __init__(self) -> None:
        self.number = 0
        self.display = ""
        self.process: subprocess.Popen[bytes] | None = None

    @staticmethod
    def _free_display() -> int:
        for number in range(90, 200):
            if not Path(f"/tmp/.X{number}-lock").exists() and not Path(
                f"/tmp/.X11-unix/X{number}"
            ).exists():
                return number
        raise RuntimeError("no free X display number is available")

    def __enter__(self) -> _XvfbDisplay:
        self.number = self._free_display()
        self.display = f":{self.number}"
        # WSL exposes a read-only /tmp/.X11-unix, so the display must use an
        # abstract socket instead of a filesystem one.
        self.process = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", "1280x800x24", "-nolisten", "unix"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Xvfb exited before the probe could use it")
            probe = subprocess.run(
                ["xdpyinfo", "-display", self.display],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            if probe.returncode == 0:
                return self
            time.sleep(0.2)
        raise RuntimeError("Xvfb did not start a usable display")

    def __exit__(self, *_exc: object) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        with contextlib.suppress(OSError):
            Path(f"/tmp/.X{self.number}-lock").unlink()


@pytest.mark.skipif(not _xvfb_available(), reason="Xvfb is required for a controlled display")
@pytest.mark.skipif(not DIST.is_file(), reason="run npm run build in frontend/ first")
@pytest.mark.full_runtime
@pytest.mark.parametrize("allow_external_connect", [False, True], ids=["production", "relaxed-connect"])
def test_production_csp_is_enforced_by_webkit(tmp_path, allow_external_connect):
    dist = DIST
    if allow_external_connect:
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_csp_webview import _non_loopback_ipv4

        denied_host = _non_loopback_ipv4()
        dist = shutil.copytree(DIST.parent, tmp_path / "bundle") / DIST.name
        html = dist.read_text(encoding="utf-8")
        assert "connect-src 'self'" in html
        dist.write_text(
            html.replace("connect-src 'self'", f"connect-src http://{denied_host}:* 'self'"),
            encoding="utf-8",
        )
    report = tmp_path / "csp-webview.json"
    environment = {
        **os.environ,
        "GDK_BACKEND": "x11",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "WEBKIT_DISABLE_DMABUF_RENDERER": "1",
    }
    environment.pop("WAYLAND_DISPLAY", None)
    with _XvfbDisplay() as display:
        environment["DISPLAY"] = display.display
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--dist",
                str(dist),
                "--report",
                str(report),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            env=environment,
        )
    assert completed.returncode == int(allow_external_connect), completed.stdout + completed.stderr
    evidence = json.loads(report.read_text(encoding="utf-8"))
    results = evidence["results"]
    assert all(row["controlObserved"] == "allowed" for row in results if "controlObserved" in row)
    failed = [row for row in results if not row["passed"]]
    if allow_external_connect:
        assert len(failed) == 2, failed
        assert all(row["directive"] == "connect-src" and row["observed"] == "allowed" for row in failed)
    else:
        assert not failed, failed
    assert any("Refused to" in line for line in evidence["engineReports"])
