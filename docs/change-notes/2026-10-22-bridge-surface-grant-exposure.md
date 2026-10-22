# 2026-10-22 — Bridge surface: the page could mint its own source-read grant

Issue #59 added the picker-grant boundary to `DesktopApi`: source reads require a folder the user chose through the native picker, and output writes require a separate destination grant. The boundary itself was correct. The problem was that it sat on the wrong side of the bridge.

`webview.util.get_functions` builds `window.pywebview.api` by walking `dir(js_api)` **recursively** and publishing every attribute that neither starts with `_` nor carries `_serializable = False`. `previewgen/desktop_runtime.py` passes the whole `DesktopApi` as `js_api`, so a rendered document received:

- `add_authorized_folder`, `add_authorized_input_folder`, `add_authorized_output_folder` — the capability mutators that are supposed to be reachable only from native picker callbacks,
- `is_authorized_*` — the authorization oracles,
- `set_window` and, once the runtime had bound the native window, the entire `webview.Window` object graph,
- 104 internal coordination methods reached through public attributes (`preview_coordinator.submit_preview`, `lifecycle.scanner.start_scan`, `preview_server.publish_jpeg`, `lifecycle.cancel_event.wait`, …). Calling a coordinator directly skips every check `DesktopApi` performs.

Measured live, in a real WebKit window, against the code as it stood on `main`:

```text
bridge entries visible to the page : 146
  of which nested internal objects : 104
  grant mutators                   : add_authorized_folder, add_authorized_input_folder, add_authorized_output_folder
read /tmp/…/not-selected.png       : {"ok": false, "error": "UNAUTHORIZED_SOURCE"}
page calls add_authorized_input_folder("/tmp/…") then re-reads the same file
                                   : {"ok": true, "status": "queued"}   ← SELF-GRANT BYPASS CONFIRMED
```

## Fix

No new mechanism, only the two pywebview already documents:

1. Grant mutators and authorization oracles are underscore-private again (`_add_authorized_folder`, `_is_authorized_input_path`, `_is_authorized_export_destination`, `_is_authorized_selected_file`, `_set_window`). Native runtime code calls them by their private names; `previewgen/desktop_runtime.py:130` is the only production caller outside `api.py`.
2. The native window handle moved from `self.window` to `self._window`, so binding it cannot publish a `webview.Window` to the page.
3. The objects that hold internal state — `ScannerService`, `LifecycleManager`, `PreviewFileServer`, `PreviewCoordinator`, `ProbeCoordinator`, `ThumbnailCoordinator` — carry `_serializable = False`, which is the check `get_functions` applies before recursing.

After the fix, in the same harness:

```text
bridge entries visible to the page : 33
  nested internal objects          : 0
  grant mutators                   : (none)
read an un-picked file             : {"ok": false, "error": "UNAUTHORIZED_SOURCE"}   ← SELF-GRANT DENIED
```

The 33 remaining entries are the flat operations the frontend actually calls, plus a few (`has_outstanding_work`, `cleanup`, `scan_folder`, `browse_font`, `browse_logo`, `browse_input_folder`, `browse_output_folder`) that grant nothing.

## Guard

`tests/unit/test_bridge_surface_exposure.py` re-implements the `get_functions` walk over a live `DesktopApi` and pins the result to an explicit frozenset. Any new public method — or any public attribute that holds an object graph — fails the test until someone adds it to the list on purpose. A second assertion proves that binding a window leaks no nested names, and a third proves no grant mutator exists on the class at all.

Local execution:

```bash
python -m pytest tests/ -q
ruff check .
```

334 passed, 3 skipped under `xvfb-run`; `ruff check .` clean.
