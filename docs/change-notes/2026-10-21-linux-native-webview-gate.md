# Frozen Linux app now opens a real WebView — 2026-10-21

## Problem
`previewgen/desktop_runtime.py` checks `find_spec("gi")` before creating a window and,
when it is absent, logs "Linux system GTK/QT python bindings not present", writes the
`PREVIEWGEN_READY_MARKER`, and returns `0`. Because PyGObject was in none of the project
requirement files, the frozen Linux build could never contain `gi`. The result: every
Linux GUI smoke gate passed **without ever loading a WebView**, so the green checkmark
proved only that the process started. This contradicts the standing rule in
`2026-10-21-local-release-gate.md`: do not describe a skipped check as a passed test.

## Root causes (four, all had to be fixed together)
1. **Missing dependency.** `pywebview` is pure-Python; its Linux backends are PyGObject
   bindings. `requirements.in` pinned `pywebview` but never `PyGObject`, so `gi` was
   unimportable in the build env and therefore absent from the bundle.
2. **Source-only package.** PyGObject publishes no wheels for any version (verified
   against PyPI up to 3.58.1), so the hash-pinned install step compiles it and needs
   `gobject-introspection`/`cairo` headers plus `pkg-config` *before* it runs.
   `build.yml` installed those after the lock step, and never installed the headers at all.
3. **No PyInstaller WebKit2 hook.** PyInstaller ships `hook-gi.repository.*` for many
   namespaces and a matching `pre_safe_import_module` alias for each. Neither exists for
   `WebKit2`, which pywebview imports at `webview/platforms/gtk.py:44`. Without the alias
   the module stays a "missing module" in modulegraph, so no hook can attach and the
   `WebKit2-4.1.typelib` is never collected. `Soup` is already covered upstream.
4. **Version ceiling on the runner.** PyGObject 3.52.0 moved from the girepository-1.0 to
   the girepository-2.0 headers, and ubuntu-22.04 (our runner) has no
   `libgirepository-2.0-dev` package at all (Launchpad returns zero published binaries for
   it). Pinning `>=3.48,<3.52` keeps the build compilable there.

## Changes
- `requirements.in`: added `PyGObject>=3.48,<3.52; sys_platform == 'linux'` with the
  runner constraint documented in place. Windows (WebView2) and macOS (Cocoa) are
  unaffected by the marker.
- `requirements-lock.txt` / `requirements-dev-lock.txt`: regenerated with the documented
  `uv pip compile --universal --generate-hashes --python-version 3.12` command. Resolution
  adds `pygobject==3.50.2` and `pycairo==1.29.2` (Linux markers only).
- `hooks/hook-gi.repository.WebKit2.py`: collects the WebKit2 typelib and its shared
  libraries, preferring the 4.1 stack and falling back to 4.0 exactly like pywebview.
- `hooks/pre_safe_import_module/hook-gi.repository.WebKit2.py`: registers the namespace as
  a runtime module so PyInstaller will run the collector hook above.
- `.github/workflows/build.yml`: moved the Linux system-dependency step **above** the
  lock install, added `gir1.2-webkit2-4.1`, `gir1.2-gtk-3.0`, `libgirepository1.0-dev`,
  `libcairo2-dev`, `pkg-config`, `python3-dev`, and passed `--additional-hooks-dir hooks`
  on Linux builds (typelibs must exist on the build host for the hooks to find them).

## Local verification (WSL2, Ubuntu 26.04 host)
Built with the same PyInstaller flags CI now uses, from a Python 3.12.14 venv synced to
the regenerated `--require-hashes` dev lock:

- Bundle now contains `gi/` and 17 GIR typelibs including `WebKit2-4.1` and `Soup-3.0`.
- `xvfb-run ./dist/PreviewGen/PreviewGen --gui-smoke-test` → exit `0`, marker written, and
  the headless-fallback warning is **gone**. Log shows `Loading frontend from: …/_internal/frontend/dist/index.html`
  followed by `Frontend mounted and reported ready.` That line is emitted by
  `DesktopApi.frontend_ready()` (`previewgen/api.py:310`), which is only reachable when the
  React bundle actually executes inside the window and calls across the pywebview bridge —
  so the gate now proves a live WebView round-trip instead of a process start.
- `--smoke-test` → `[STARTUP-TEST] OK`, 42 formats.
- `--render-test-all --fixtures tests/fixtures` → all 9 fixtures passed.
- `PREVIEWGEN_RELEASE_GATE=1 pytest tests/integration/test_release_renderers_gate.py -W error`
  → 15 passed.
- `python -m ruff check .` → clean; `PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE=1 pytest tests/`
  → 295 passed, 3 skipped.

A clean `pip install --require-hashes -r requirements-dev-lock.txt` into an empty venv was
also verified to build PyGObject from its hashed sdist and import `gi`.

## Not covered / still open
- **Ubuntu 22.04 build path is unverified.** The dev headers and typelibs listed for
  `build.yml` were confirmed to exist for jammy amd64 via the Launchpad API, and the
  `<3.52` ceiling was chosen because of what jammy lacks, but the CI job itself cannot be
  run here (hosted Actions minutes are exhausted) and my verification host is Ubuntu
  26.04. Treat the first Linux Actions run as the real acceptance test.
- **Bundle grew to ~399 MB** on Linux because the GTK/WebKit library graph is now bundled.
  Artifact size, AppImage start-up time, and end-user GTK conflicts (system vs. bundled
  typelibs) still need measuring on a real runner.
- Native Windows (WebView2 idle/freeze #19) and macOS (Cocoa, notarization) behaviour,
  installers, signing, and checksums remain Actions/manual release gates.
- The app still falls back headlessly if a future runner lacks the typelibs; the fallback
  is now only silent-with-a-warning, and this change does not make it fail closed.
