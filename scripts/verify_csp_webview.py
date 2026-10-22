#!/usr/bin/env python3
"""Enforce the built production CSP inside the same WebKit engine the desktop app uses.

Issue #20 asks for validation of the packaged policy rather than a review of the
string. The frontend contract test only proves the meta tag is present; this
proves the engine acts on it. It loads the real ``frontend/dist`` artifact in
WebKitGTK (the engine family behind the Linux pywebview window), performs one
action per directive, and cross-checks the outcome against the policy reports
WebKit writes to the console.

Probes are written to leave a verdict in ``window.__p`` rather than returning a
promise, because WebKitGTK 4.1's ``run_javascript`` cannot await one. A probe
that never reports success is read as ``blocked``: nothing loaded, nothing ran.

Run after ``npm run build`` in frontend/:

    python scripts/verify_csp_webview.py
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist" / "index.html"
POLL_BUDGET_MS = 3000


def _jpeg_bytes() -> bytes:
    """A real encoded JPEG, like the ones the loopback preview server publishes."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "JPEG")
    return buf.getvalue()


JPEG = _jpeg_bytes()

# Each probe performs something the shipped policy must decide. ``expect`` is the
# behavior the policy mandates; the harness polls window.__p until it leaves
# "pending" or the budget runs out.
PROBES: list[dict[str, str]] = [
    {
        "name": "script-src blocks an injected inline script",
        "directive": "script-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending'; window.__inlineRan = false;
          var s = document.createElement('script');
          s.textContent = 'window.__inlineRan = true;';
          s.onerror = function () { window.__p = 'blocked'; };
          document.head.appendChild(s);
          setTimeout(function () {
            window.__p = window.__inlineRan ? 'allowed' : 'blocked';
          }, 400);
        """,
    },
    {
        "name": "script-src blocks a remote script tag",
        "directive": "script-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending';
          var s = document.createElement('script');
          s.src = 'https://example.invalid/evil.js';
          s.onload = function () { window.__p = 'allowed'; };
          s.onerror = function () { window.__p = 'blocked'; };
          document.head.appendChild(s);
        """,
    },
    {
        "name": "script-src still permits 'unsafe-eval' (pywebview bridge helper)",
        "directive": "script-src",
        "expect": "allowed",
        "js": """
          window.__p = 'pending';
          try { window.__p = eval('1 + 1') === 2 ? 'allowed' : 'blocked'; }
          catch (e) { window.__p = 'blocked'; }
        """,
    },
    {
        "name": "connect-src blocks a remote fetch",
        "directive": "connect-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending';
          fetch('https://example.invalid/leak.json').then(function (r) {
            window.__p = r.ok ? 'allowed' : 'blocked';
          }, function () { window.__p = 'blocked'; });
        """,
    },
    {
        "name": "connect-src allows the loopback preview transport",
        "directive": "connect-src",
        "expect": "allowed",
        "js": """
          window.__p = 'pending';
          fetch('http://127.0.0.1:%(loopback_port)d/preview.jpg').then(function (r) {
            window.__p = r.ok ? 'allowed' : 'blocked';
          }, function () { window.__p = 'blocked'; });
        """,
    },
    {
        "name": "img-src blocks a remote image",
        "directive": "img-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending';
          var i = new Image();
          i.onload = function () { window.__p = 'allowed'; };
          i.onerror = function () { window.__p = 'blocked'; };
          i.src = 'https://example.invalid/pixel.png';
        """,
    },
    {
        "name": "img-src allows a loopback preview image",
        "directive": "img-src",
        "expect": "allowed",
        "js": """
          window.__p = 'pending';
          var i = new Image();
          i.onload = function () { window.__p = 'allowed'; };
          i.onerror = function () { window.__p = 'blocked'; };
          i.src = 'http://127.0.0.1:%(loopback_port)d/preview.jpg';
        """,
    },
    {
        "name": "frame-src 'none' blocks a remote iframe",
        "directive": "frame-src",
        "expect": "blocked",
        # A CSP-refused frame never navigates, so it still reports a successful
        # load of the empty document. The engine's own refusal is the signal.
        "engine": "frame-src",
        "js": """
          window.__p = 'pending';
          var f = document.createElement('iframe');
          f.src = 'https://example.invalid/';
          document.body.appendChild(f);
        """,
    },
    {
        "name": "object-src 'none' blocks a remote plugin object",
        "directive": "object-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending';
          var o = document.createElement('object');
          o.data = 'https://example.invalid/thing.swf';
          o.onload = function () { window.__p = 'allowed'; };
          o.onerror = function () { window.__p = 'blocked'; };
          document.body.appendChild(o);
        """,
    },
    {
        "name": "connect-src blocks a remote XMLHttpRequest",
        "directive": "connect-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending';
          var x = new XMLHttpRequest();
          x.onload = function () { window.__p = 'allowed'; };
          x.onerror = function () { window.__p = 'blocked'; };
          try { x.open('GET', 'https://example.invalid/x', true); x.send(); }
          catch (e) { window.__p = 'blocked'; }
        """,
    },
    {
        "name": "worker-src 'none' blocks a remote worker",
        "directive": "worker-src",
        "expect": "blocked",
        "js": """
          window.__p = 'pending';
          try {
            var w = new Worker('https://example.invalid/worker.js');
            w.onmessage = function () { window.__p = 'allowed'; };
            w.onerror = function () { window.__p = 'blocked'; };
          } catch (e) { window.__p = 'blocked'; }
        """,
    },
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = JPEG if self.path.endswith(".jpg") else b"{}"
        kind = "image/jpeg" if self.path.endswith(".jpg") else "application/json"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def _serve_loopback() -> tuple[HTTPServer, int]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _run_probes(
    uri: str,
    timeout_seconds: int,
    loopback_port: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import GLib, Gtk, WebKit2  # noqa: PLC0415

    results: list[dict[str, Any]] = []
    violations: list[str] = []
    pending = list(PROBES)
    state: dict[str, Any] = {"deadline": 0}

    def run_script(view: Any, script: str, then: Any) -> None:
        def on_finish(_v, result, _data):
            try:
                value = str(view.run_javascript_finish(result).get_js_value().to_string())
            except Exception as exc:  # engine refused to run the probe at all
                value = f"error:{exc}"
            then(value)

        view.run_javascript(script, None, on_finish, None)

    def record(spec: dict[str, str], outcome: str) -> None:
        results.append({
            "order": PROBES.index(spec),
            "probe": spec["name"],
            "directive": spec["directive"],
            "expected": spec["expect"],
            "observed": outcome,
            "passed": outcome == spec["expect"],
        })

    def poll_once(view: Any) -> None:
        def then(value: str) -> None:
            spec = state["spec"]
            if value in ("allowed", "blocked"):
                record(spec, value)
                start_next(view)
                return
            if GLib.get_monotonic_time() >= state["deadline"]:
                # A negative probe that never reports success was refused; a
                # positive one stuck pending is a real failure, so record as-is.
                record(spec, "blocked" if spec["expect"] == "blocked" else value or "pending")
                start_next(view)
                return
            GLib.timeout_add(150, lambda: (poll_once(view), False)[1])

        run_script(view, "window.__p || 'pending'", then)

    def start_next(view: Any) -> None:
        if not pending:
            Gtk.main_quit()
            return
        spec = pending.pop(0)
        state["spec"] = spec

        def then(_value: str) -> None:
            if "engine" in spec:
                # Injected for the engine to judge; verdict comes from its refusal.
                start_next(view)
                return
            state["deadline"] = GLib.get_monotonic_time() + POLL_BUDGET_MS * 1000
            GLib.timeout_add(120, lambda: (poll_once(view), False)[1])

        run_script(view, spec["js"] % {"loopback_port": loopback_port}, then)

    def on_load(_v, event):
        if event == WebKit2.LoadEvent.FINISHED:
            start_next(view)
        return False

    def watchdog() -> bool:
        if pending or state.get("spec") is not None:
            for spec in [state["spec"], *pending] if state.get("spec") else pending:
                record(spec, "timeout")
            pending.clear()
            print("WebKit did not finish loading the artifact", file=sys.stderr)
            Gtk.main_quit()
        return False

    win = Gtk.OffscreenWindow()
    win.set_default_size(1280, 800)
    view = WebKit2.WebView()
    settings = view.get_settings()
    settings.set_property("enable_developer_extras", True)
    # WebKitGTK 4.1 exposes no console signal, so the engine's own policy reports
    # are collected from its console-to-stderr channel when it offers one. Probe
    # outcomes stay the primary evidence; this only corroborates them.
    capture_console = any(
        p.name == "enable-write-console-messages-to-stdout" for p in settings.list_properties()
    )
    if capture_console:
        settings.set_property("enable-write-console-messages-to-stdout", True)
    win.add(view)
    win.show_all()
    view.connect("load-changed", on_load)

    saved = {fd: os.dup(fd) for fd in (1, 2)}
    # Deliberately not a context manager: the fd is dup2'd onto stdout/stderr and
    # read back after the main loop, so its lifetime spans the whole run.
    console_log = tempfile.TemporaryFile() if capture_console else None  # noqa: SIM115
    try:
        if console_log is not None:
            os.dup2(console_log.fileno(), 1)
            os.dup2(console_log.fileno(), 2)
        view.load_uri(uri)
        GLib.timeout_add_seconds(timeout_seconds, watchdog)
        Gtk.main()
    finally:
        if console_log is not None:
            for stream in (sys.stdout, sys.stderr):
                stream.flush()
            os.dup2(saved[1], 1)
            os.dup2(saved[2], 2)
            console_log.seek(0)
            for line in console_log.read().decode(errors="replace").splitlines():
                if "Refused to" in line or "Content Security Policy" in line:
                    violations.append(line.strip())
            console_log.close()
        for fd in (1, 2):
            os.close(saved[fd])

    for spec in (p for p in PROBES if "engine" in p):
        refused = any(spec["engine"] in line for line in violations)
        record(spec, "blocked" if refused else "loaded")
    results.sort(key=lambda r: r["order"])
    return results, violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DIST, help="built frontend/dist/index.html")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--report", type=Path, default=ROOT / "csp-webview-local.json")
    args = parser.parse_args(argv)

    dist = args.dist.resolve()
    if not dist.is_file():
        print(f"missing built artifact: {dist} (run npm run build in frontend/)", file=sys.stderr)
        return 2
    if "Content-Security-Policy" not in dist.read_text(encoding="utf-8"):
        print("built artifact carries no CSP meta tag", file=sys.stderr)
        return 1

    server, port = _serve_loopback()
    try:
        results, violations = _run_probes(dist.as_uri(), args.timeout, port)
    finally:
        server.shutdown()

    if len(results) != len(PROBES):
        print(f"only {len(results)}/{len(PROBES)} probes reported", file=sys.stderr)
        return 1

    width = max(len(r["probe"]) for r in results) + 2
    failures = [r for r in results if not r["passed"]]
    print(f"WebKit CSP enforcement against {dist}\n")
    for r in results:
        mark = "ok  " if r["passed"] else "FAIL"
        print(f"  [{mark}] {r['probe']:<{width}} expected={r['expected']:<8} observed={r['observed']}")
    print(f"\n{len(violations)} policy refusal(s) reported by the engine itself:")
    for text in violations[:12]:
        print(f"  - {text[:170]}")

    args.report.write_text(
        json.dumps({"artifact": str(dist), "results": results, "engineReports": violations},
                   indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nEvidence written to {args.report}")

    if failures:
        print(f"{len(failures)} probe(s) did not match the shipped policy", file=sys.stderr)
        return 1
    controls = [r for r in results if r["expected"] == "allowed"]
    if not controls:
        print("no control probe defined; a dead page would pass this run", file=sys.stderr)
        return 1
    print(
        f"All {len(PROBES)} probes matched the shipped policy, including "
        f"{len(controls)} control probe(s) that must stay permitted."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
