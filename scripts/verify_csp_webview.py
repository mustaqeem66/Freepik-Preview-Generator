#!/usr/bin/env python3
"""Enforce the built production CSP inside the same WebKit engine the desktop app uses.

Issue #20 asks for validation of the packaged policy rather than a review of the
string. The frontend contract test only proves the meta tag is present; this
proves the engine acts on it. It loads the real ``frontend/dist`` artifact in
WebKitGTK (the engine family behind the Linux pywebview window). Network
probes use a second, reachable loopback origin outside the policy allowlist.
For signals that could also be ordinary load failures, the same operation
must succeed in an unrestricted file document on the same engine. Timeouts
never count as policy refusals.

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
# behavior the policy mandates; ``control`` probes must also run without CSP.
PROBES: list[dict[str, str]] = [
    {
        "name": "script-src blocks an injected inline script",
        "directive": "script-src",
        "expect": "blocked",
        "js": """
          window.__inlineRan = false;
          var s = document.createElement('script');
          s.textContent = 'window.__inlineRan = true;';
          document.head.appendChild(s);
          window.__p = window.__inlineRan ? 'allowed' : 'blocked';
          s.remove();
        """,
    },
    {
        "name": "script-src blocks a script from a disallowed origin",
        "directive": "script-src",
        "expect": "blocked",
        "control": "allowed",
        "js": """
          window.__p = 'pending';
          var s = document.createElement('script');
          s.src = 'http://__DENIED_HOST__:%(denied_port)d/probe.js';
          s.onload = function () { window.__p = window.__probeRan ? 'allowed' : 'error'; };
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
        "name": "connect-src blocks a fetch to a disallowed origin",
        "directive": "connect-src",
        "expect": "blocked",
        "control": "allowed",
        "js": """
          window.__p = 'pending';
          fetch('http://__DENIED_HOST__:%(denied_port)d/probe.json').then(function (r) {
            window.__p = r.ok ? 'allowed' : 'error';
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
        "name": "img-src blocks an image from a disallowed origin",
        "directive": "img-src",
        "expect": "blocked",
        "control": "allowed",
        "js": """
          window.__p = 'pending';
          var i = new Image();
          i.onload = function () { window.__p = 'allowed'; };
          i.onerror = function () { window.__p = 'blocked'; };
          i.src = 'http://__DENIED_HOST__:%(denied_port)d/preview.jpg';
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
          f.src = 'http://__DENIED_HOST__:%(denied_port)d/frame.html';
          document.body.appendChild(f);
        """,
    },
    {
        "name": "object-src 'none' blocks a remote plugin object",
        "directive": "object-src",
        "expect": "blocked",
        "engine": "object-src",
        "js": """
          window.__p = 'pending';
          var o = document.createElement('object');
          o.data = 'http://__DENIED_HOST__:%(denied_port)d/object.html';
          document.body.appendChild(o);
        """,
    },
    {
        "name": "connect-src blocks an XMLHttpRequest to a disallowed origin",
        "directive": "connect-src",
        "expect": "blocked",
        "control": "allowed",
        "js": """
          window.__p = 'pending';
          var x = new XMLHttpRequest();
          x.onload = function () { window.__p = x.status === 200 ? 'allowed' : 'error'; };
          x.onerror = function () { window.__p = 'blocked'; };
          try { x.open('GET', 'http://__DENIED_HOST__:%(denied_port)d/probe.json', true); x.send(); }
          catch (e) { window.__p = 'blocked'; }
        """,
    },
    {
        "name": "worker-src 'none' blocks a blob worker",
        "directive": "worker-src",
        "expect": "blocked",
        "control": "allowed",
        "js": """
          window.__p = 'pending';
          var url = URL.createObjectURL(new Blob(
            ["postMessage('ready')"], { type: 'text/javascript' }
          ));
          try {
            var w = new Worker(url);
            w.onmessage = function (e) {
              window.__p = e.data === 'ready' ? 'allowed' : 'error';
              w.terminate();
              URL.revokeObjectURL(url);
            };
            w.onerror = function () { window.__p = 'blocked'; URL.revokeObjectURL(url); };
          } catch (e) {
            window.__p = 'blocked';
            URL.revokeObjectURL(url);
          }
        """,
    },
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/preview.jpg":
            body, kind = JPEG, "image/jpeg"
        elif self.path == "/probe.js":
            body, kind = b"window.__probeRan = true;", "text/javascript"
        elif self.path in ("/frame.html", "/object.html"):
            body, kind = b"<!doctype html><title>PreviewGen CSP probe</title>", "text/html"
        elif self.path == "/probe.json":
            body, kind = b"{}", "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def _serve_loopback(host: str) -> tuple[HTTPServer, int]:
    server = HTTPServer((host, 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_port


def _non_loopback_ipv4() -> str:
    """The host's own non-loopback IPv4 address.

    The denied origin must be reachable for the control run to mean anything.
    A second loopback address is not: WebKit's sandboxed network process
    cannot open a connection to it, so the control would time out and the
    probe could not tell a policy refusal from an unreachable host.
    """
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # Connecting a datagram socket only selects a route; it sends nothing.
            probe.connect(("192.0.2.1", 9))
            candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except OSError:
        pass
    for address in candidates:
        if not address.startswith("127."):
            return address
    raise RuntimeError("no reachable non-loopback IPv4 address is available for the CSP control")


def _run_probes(
    uri: str,
    timeout_seconds: int,
    loopback_port: int,
    denied_port: int,
    denied_host: str,
    specs: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import GLib, Gtk, WebKit2  # noqa: PLC0415

    results: list[dict[str, Any]] = []
    violations: list[str] = []
    pending = iter(specs)
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
            if value in ("allowed", "blocked", "error"):
                record(spec, value)
                start_next(view)
                return
            if GLib.get_monotonic_time() >= state["deadline"]:
                record(spec, "timeout")
                start_next(view)
                return
            GLib.timeout_add(150, lambda: (poll_once(view), False)[1])

        run_script(view, "window.__p || 'pending'", then)

    def start_next(view: Any) -> None:
        spec = next(pending, None)
        if spec is None:
            state["spec"] = None
            Gtk.main_quit()
            return
        state["spec"] = spec

        def then(value: str) -> None:
            if value.startswith("error:"):
                record(spec, "probe-error")
                results[-1]["error"] = value
                start_next(view)
                return
            if "engine" in spec:
                # Injected for the engine to judge; verdict comes from its refusal.
                start_next(view)
                return
            state["deadline"] = GLib.get_monotonic_time() + POLL_BUDGET_MS * 1000
            GLib.timeout_add(120, lambda: (poll_once(view), False)[1])

        source = (
            spec["js"] % {"loopback_port": loopback_port, "denied_port": denied_port}
        ).replace("__DENIED_HOST__", denied_host)
        # Returning a DOM node or a Promise reports an unsupported result
        # after executing the code. Only poll the scalar verdict separately.
        run_script(view, f"(() => {{\n{source}\nreturn true;\n}})()", then)

    def on_load(_v, event):
        if event == WebKit2.LoadEvent.FINISHED:
            start_next(view)
        return False

    def watchdog() -> bool:
        state["watchdog"] = None
        if state.get("spec") is not None:
            record(state["spec"], "timeout")
        for spec in pending:
            record(spec, "timeout")
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
        state["watchdog"] = GLib.timeout_add_seconds(timeout_seconds, watchdog)
        Gtk.main()
    finally:
        if state.get("watchdog") is not None:
            GLib.source_remove(state["watchdog"])
        win.destroy()
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

    reported = {row["order"] for row in results}
    for spec in (p for p in specs if "engine" in p and PROBES.index(p) not in reported):
        path = spec["directive"].split("-")[0] + ".html"
        url = f"http://{denied_host}:{denied_port}/{path}"
        refused = any(url in line and spec["engine"] in line for line in violations)
        record(spec, "blocked" if refused else "no-policy-refusal")
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

    loopback, port = _serve_loopback("127.0.0.1")
    try:
        denied_host = _non_loopback_ipv4()
        denied, denied_port = _serve_loopback(denied_host)
        try:
            results, violations = _run_probes(dist.as_uri(), args.timeout, port, denied_port, denied_host, PROBES)
            control_specs = [spec for spec in PROBES if "control" in spec]
            with tempfile.TemporaryDirectory(prefix="previewgen-csp-") as scratch:
                control = Path(scratch) / "index.html"
                control.write_text("<!doctype html><meta charset=utf-8><title>CSP control</title>", encoding="utf-8")
                baseline, _ = _run_probes(control.as_uri(), args.timeout, port, denied_port, denied_host, control_specs)
        finally:
            denied.shutdown()
            denied.server_close()
    finally:
        loopback.shutdown()
        loopback.server_close()

    controls_by_order = {row["order"]: row["observed"] for row in baseline}
    for row in results:
        if "control" in PROBES[row["order"]]:
            outcome = controls_by_order.get(row["order"], "missing")
            row["controlObserved"] = outcome
            row["passed"] = row["passed"] and outcome == "allowed"

    if len(results) != len(PROBES):
        print(f"only {len(results)}/{len(PROBES)} probes reported", file=sys.stderr)
        return 1

    width = max(len(r["probe"]) for r in results) + 2
    failures = [r for r in results if not r["passed"]]
    print(f"WebKit CSP enforcement against {dist}\n")
    for r in results:
        mark = "ok  " if r["passed"] else "FAIL"
        control_note = f" unrestricted={r['controlObserved']}" if "controlObserved" in r else ""
        print(f"  [{mark}] {r['probe']:<{width}} expected={r['expected']:<8} observed={r['observed']}{control_note}")
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
