#!/usr/bin/env python3
"""Enforce WCAG AA text contrast against the built production bundle.

The stylesheet-level checks in tests/frontend/test_theme_contrast.py read the
CSS source. That proves a token is readable *in isolation*, but the shipped
palette is assembled from five ``:root`` blocks spread across three files, and
the last import wins. A colour that looks correct in one file can therefore be
silently overridden by another -- which is exactly how the studio badge, the
format notes and the slider hints kept landing between 3.92:1 and 4.41:1 while
their token was "fixed" in a file that never reached the browser.

This gate closes that gap. It loads the real ``frontend/dist`` artifact in
WebKitGTK -- the engine family behind the Linux pywebview window -- measures the
*computed* foreground and background of every rendered text node in both
themes, and fails when any of them falls below the WCAG AA floor (4.5:1 for
normal text, 3:1 for large text).

Run after ``npm run build`` in frontend/:

    python scripts/verify_theme_contrast.py
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
REPORT = ROOT / "theme-contrast-local.json"
LOAD_BUDGET_MS = 15000

# The theme attribute the app writes onto <html>; the demo bridge renders the
# full studio UI in the browser fallback, so the same document covers both.
THEMES = ("light", "dark")

# The gate measures the *resolved palette*, so it must never sample an
# animation frame. The studio animates background-color when the theme
# changes; `getComputedStyle` returns the interpolated value mid-animation,
# which once made the dark theme report its dark foreground against the
# light theme's still-animating background and failed the gate on colours
# the app never actually displayed.
#
# This must run before the theme toggle, not at measurement time: the
# animation has already started by the time the second theme is measured, so
# disabling the transition afterwards would sample the frame that is already
# on screen.
SETTLE_JS = r"""
(function () {
  var style = document.createElement('style');
  style.setAttribute('data-contrast-gate', '1');
  style.textContent = '*, *::before, *::after { transition: none !important; }';
  (document.head || document.documentElement).appendChild(style);
  return 'settled';
})()
"""

# Runs inside the page. Reports every rendered text node with the colours the
# engine actually resolved, so a cascade override cannot hide from the gate.
MEASURE_JS = r"""
(function () {
  function srgb(c) { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
  function luminance(rgb) {
    return 0.2126 * srgb(rgb[0]) + 0.7152 * srgb(rgb[1]) + 0.0722 * srgb(rgb[2]);
  }
  function ratio(a, b) {
    var hi = luminance(a), lo = luminance(b);
    if (hi < lo) { var t = hi; hi = lo; lo = t; }
    return (hi + 0.05) / (lo + 0.05);
  }
  function parse(color) {
    var text = String(color);
    // WebKit reports some colors as color(srgb r g b / a) with 0..1 channels.
    var srgb = text.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)/);
    if (srgb) {
      return [parseFloat(srgb[1]) * 255, parseFloat(srgb[2]) * 255,
              parseFloat(srgb[3]) * 255, srgb[4] ? parseFloat(srgb[4]) : 1];
    }
    var m = text.match(/[\d.]+/g);
    if (!m) return null;
    return [parseFloat(m[0]), parseFloat(m[1]), parseFloat(m[2]),
            m.length > 3 ? parseFloat(m[3]) : 1];
  }
  // Walk up for the first opaque background; a translucent layer composites
  // over whatever it sits on, so the nearest opaque ancestor is the real base.
  function backgroundOf(el) {
    var node = el;
    while (node && node !== document.documentElement) {
      var c = parse(getComputedStyle(node).backgroundColor);
      if (c && c[3] > 0.9) return c.slice(0, 3);
      node = node.parentElement;
    }
    var body = parse(getComputedStyle(document.body).backgroundColor);
    return body ? body.slice(0, 3) : [255, 255, 255];
  }
  function describe(el, text, fg, bg, size, weight) {
    var large = size >= 24 || (size >= 18.66 && weight >= 700);
    return {
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string') ? el.className.slice(0, 60) : '',
      text: text.replace(/\s+/g, ' ').slice(0, 60),
      fg: fg, bg: 'rgb(' + bg.join(',') + ')',
      size: size, weight: weight,
      floor: large ? 3 : 4.5,
      ratio: Math.round(ratio(fg, bg) * 100) / 100,
    };
  }
  var out = [];
  var selector = 'button,a,label,h1,h2,h3,h4,p,span,li,td,th,div,strong,em,output,summary';
  var nodes = document.querySelectorAll(selector);
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    // Only elements that render their own text node; a wrapper that merely
    // contains other text would double-count the same pixels.
    var text = '';
    for (var j = 0; j < el.childNodes.length; j++) {
      if (el.childNodes[j].nodeType === 3) text += el.childNodes[j].nodeValue;
    }
    text = text.trim();
    if (!text || text.length > 120) continue;
    var cs = getComputedStyle(el);
    var rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) continue;
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (parseFloat(cs.opacity) < 0.5) continue;
    var fg = parse(cs.color);
    if (!fg) continue;
    var bg = backgroundOf(el);
    out.push(describe(el, text, fg.slice(0, 3), bg,
      parseFloat(cs.fontSize), parseInt(cs.fontWeight, 10) || 400));
  }
  // A placeholder is text the user is expected to read. WebKitGTK does not
  // implement ::placeholder, so the engine reports the input's own colour
  // here; the token that drives it is checked by the stylesheet test instead.
  return JSON.stringify(out);
})()
"""


class _Handler(BaseHTTPRequestHandler):
    """Serves the built bundle; every other path falls back to index.html."""

    def do_GET(self) -> None:  # noqa: N802
        dist = self.server.dist  # type: ignore[attr-defined]
        path = (self.path.split("?", 1)[0] or "/").lstrip("/")
        target = (dist / path).resolve() if path else dist / "index.html"
        if not target.is_file() or dist.resolve() not in target.parents:
            target = dist / "index.html"
        body = target.read_bytes()
        kind = "text/html; charset=utf-8"
        if target.suffix == ".js":
            kind = "text/javascript; charset=utf-8"
        elif target.suffix == ".css":
            kind = "text/css; charset=utf-8"
        elif target.suffix == ".svg":
            kind = "image/svg+xml"
        elif target.suffix in (".png", ".jpg", ".jpeg", ".webp", ".ico"):
            kind = "image/" + target.suffix.lstrip(".")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def _serve_dist(dist: Path) -> tuple[HTTPServer, int]:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = HTTPServer(("127.0.0.1", port), _Handler)
    server.dist = dist  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _measure(dist: Path, timeout_seconds: int) -> dict[str, Any]:
    """Load the bundle in WebKitGTK and measure both themes."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import GLib, Gtk, WebKit2  # noqa: PLC0415

    server, port = _serve_dist(dist)
    uri = f"http://127.0.0.1:{port}/index.html"
    measured: dict[str, Any] = {}
    state: dict[str, Any] = {"theme": None, "done": False}

    def run_script(view: Any, script: str, then: Any) -> None:
        def on_finish(_v: Any, result: Any, _data: Any) -> None:
            try:
                value = str(view.run_javascript_finish(result).get_js_value().to_string())
            except Exception as exc:  # the engine refused the probe entirely
                value = f"error:{exc}"
            then(value)

        view.run_javascript(script, None, on_finish, None)

    def measure_theme(view: Any) -> None:
        theme = state["theme"]

        def then(value: str) -> None:
            if value.startswith("error:"):
                measured[theme] = {"error": value}
            else:
                try:
                    measured[theme] = json.loads(value)
                except json.JSONDecodeError:
                    measured[theme] = {"error": "unparseable measurement"}
            state["theme"] = None
            next_theme(view)

        run_script(view, MEASURE_JS, then)

    def apply_theme(view: Any) -> None:
        # React owns the theme and re-applies data-theme from its own state, so
        # setting the attribute directly is overwritten. Drive the real toggle
        # control instead: that exercises the same path the user takes.
        def then(value: str) -> None:
            if value != "clicked":
                measured[state["theme"]] = {
                    "error": "the theme toggle control was not found; the app did not render the studio UI"
                }
                state["theme"] = None
                next_theme(view)
                return
            measure_theme(view)

        run_script(
            view,
            "var t = document.querySelector('button.theme-toggle');"
            "if (t) { t.click(); 'clicked'; } else { 'missing'; }",
            then,
        )

    def next_theme(view: Any) -> None:
        pending = [t for t in THEMES if t not in measured]
        if not pending:
            state["done"] = True
            Gtk.main_quit()
            return
        state["theme"] = pending[0]
        if state["theme"] == THEMES[0]:
            # The app starts in the first theme, so measure it as it is.
            measure_theme(view)
        else:
            apply_theme(view)

    def on_load(_v: Any, event: Any) -> bool:
        if event == WebKit2.LoadEvent.FINISHED:
            # The studio mounts asynchronously: the browser fallback bridge
            # waits out the pywebview handshake before rendering, so measuring
            # straight after load sees an empty document. Poll until the app
            # has actually painted its controls.
            wait_for_render(view)
        return False

    def wait_for_render(view: Any, attempt: int = 0) -> None:
        def then(value: str) -> None:
            if value == "ready" or attempt >= 120:
                # Disable transitions before any theme is measured, so every
                # colour the gate reads is the settled one rather than an
                # interpolated frame.
                run_script(view, SETTLE_JS, lambda _settled: next_theme(view))
                return
            GLib.timeout_add(250, lambda: (wait_for_render(view, attempt + 1), False)[1])

        run_script(
            view,
            "document.querySelectorAll('button').length > 10 ? 'ready' : 'pending'",
            then,
        )

    def watchdog() -> bool:
        if not state["done"]:
            print("WebKit did not finish measuring the artifact", file=sys.stderr)
            Gtk.main_quit()
        return False

    win = Gtk.OffscreenWindow()
    win.set_default_size(1440, 900)
    view = WebKit2.WebView()
    win.add(view)
    win.show_all()
    view.connect("load-changed", on_load)

    try:
        view.load_uri(uri)
        GLib.timeout_add_seconds(timeout_seconds, watchdog)
        Gtk.main()
    finally:
        server.shutdown()
        server.server_close()
    return measured


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DIST, help="built frontend/dist")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)

    dist = args.dist.resolve()
    if dist.is_file():
        # Accept either the bundle directory or the index.html inside it.
        dist = dist.parent
    index = dist / "index.html"
    if not index.is_file():
        print(f"missing built artifact: {index} (run npm run build in frontend/)", file=sys.stderr)
        return 2

    measured = _measure(dist, args.timeout)

    failures: list[dict[str, Any]] = []
    for theme in THEMES:
        rows = measured.get(theme)
        if rows is None:
            print(f"theme {theme!r} was never measured", file=sys.stderr)
            return 1
        if isinstance(rows, dict) and "error" in rows:
            print(f"theme {theme!r} measurement failed: {rows['error']}", file=sys.stderr)
            return 1
        failures.extend({"theme": theme, **row} for row in rows if row["ratio"] < row["floor"])

    # The two themes must actually be different. If the toggle did not take
    # effect, both passes would report the same colours and the dark theme
    # would never be checked at all.
    if len(THEMES) == 2:
        light_colours = {tuple(row["fg"]) for row in measured[THEMES[0]]}
        dark_colours = {tuple(row["fg"]) for row in measured[THEMES[1]]}
        if light_colours == dark_colours:
            print(
                "both themes resolved to the same foreground colours; the theme "
                "toggle did not take effect, so the dark theme was not measured",
                file=sys.stderr,
            )
            return 1

    report = {
        "artifact": str(index),
        "themes": {t: len(measured.get(t, [])) for t in THEMES},
        "failures": failures,
    }
    args.report.write_text(json.dumps(report, indent=1), encoding="utf-8")

    total = sum(report["themes"].values())
    print(f"WebKit theme contrast against {index}\n")
    for theme in THEMES:
        rows = measured.get(theme, [])
        bad = [r for r in rows if r["ratio"] < r["floor"]]
        print(f"  {theme:5} {len(rows):4} text elements, {len(bad)} below the WCAG AA floor")
    if failures:
        print("\nFAIL:")
        for f in failures:
            print(
                f"  {f['theme']:5} {f['ratio']:.2f}:1 (floor {f['floor']}) "
                f'{f["size"]} {f["tag"]}.{f["cls"]} "{f["text"]}" '
                f"fg={f['fg']} bg={f['bg']}"
            )
        print(f"\nEvidence written to {args.report}")
        return 1
    print(f"\nAll {total} rendered text elements clear WCAG AA in both themes.")
    print(f"Evidence written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
