# Frozen Linux app now opens a real WebView — 2026-10-21

## Problem
`previewgen/desktop_runtime.py` checked `find_spec("gi")` before creating a window and,
when it was absent, logged a warning, wrote the `PREVIEWGEN_READY_MARKER`, and returned
`0`. PyGObject was in none of the project requirement files, so the frozen Linux build
could never contain `gi`. Every Linux GUI smoke gate therefore passed **without ever
loading a WebView** — the green checkmark proved only that the process started. This
contradicts the standing rule in `2026-10-21-local-release-gate.md`: do not describe a
skipped check as a passed test.

## Root causes (four, all had to be fixed together)
1. **Missing dependency.** `pywebview` is pure-Python; its Linux backends are PyGObject
   bindings. `requirements.in` pinned `pywebview` but never `PyGObject`, so `gi` was
   unimportable in the build env and absent from the bundle.
2. **Source-only package.** PyGObject publishes no wheels for any version, so pip compiles
   it and needs gobject-introspection/cairo headers plus `pkg-config` *before* the lock
   install runs. `build.yml` installed system packages after that step, and never
   installed the headers at all.
3. **No PyInstaller WebKit2 hook.** PyInstaller ships `hook-gi.repository.*` and a matching
   `pre_safe_import_module` alias for most namespaces; neither exists for `WebKit2`, which
   pywebview imports at `webview/platforms/gtk.py:44`. Without the alias the module stays a
   "missing module" in modulegraph, so no hook can attach and `WebKit2-4.1.typelib` is never
   collected.
4. **Version ceiling on the runner.** PyGObject 3.52.0 moved from the girepository-1.0 to
   the girepository-2.0 headers, and ubuntu-22.04 has no `libgirepository-2.0-dev` package.
   `>=3.48,<3.52` keeps the build compilable there.

## Change: PyGObject lives in its own lock, not in the shared ones
The first attempt added `PyGObject` to `requirements.in`, which puts it into
`requirements-dev-lock.txt`. That breaks every pull request: `pr-checks.yml` installs that
lock on ubuntu-22.04 with no apt step, so the install would die compiling gi bindings
before running a single test, and it is also the contributor install command documented in
`README.md`.

Instead `requirements-linux-gui.in` compiles `-c requirements-dev-lock.txt` plus
`PyGObject`, producing `requirements-linux-gui-lock.txt`, which only the Linux packaging
job installs. `pr-checks.yml`, `requirements-dev-lock.txt`, `requirements-lock.txt` and the
README are untouched, so nothing outside the Linux release build changes.

The constraint is load-bearing: without it uv re-resolves the graph and the Linux bundle
silently ships different `psd-tools`/`pyinstaller-hooks-contrib`/`setuptools` versions than
the macOS and Windows bundles. `diff` of the version lines between the two locks now shows
exactly two additions, `pycairo` and `pygobject`, both Linux-markered.

## Changes
- `requirements-linux-gui.in` / `requirements-linux-gui-lock.txt` (new): Linux-only GUI
  build environment, constrained to the dev lock.
- `hooks/hook-gi.repository.WebKit2.py`: collects the WebKit2 typelib and shared libraries,
  preferring 4.1 and falling back to 4.0 exactly like pywebview.
- `hooks/pre_safe_import_module/hook-gi.repository.WebKit2.py`: registers the namespace as a
  runtime module so the collector hook above runs.
- `.github/workflows/build.yml`: Linux system-dependency step moved **above** the lock
  install and extended with `gir1.2-webkit2-4.1`, `gir1.2-gtk-3.0`, `libgirepository1.0-dev`,
  `libcairo2-dev`, `pkg-config`, `python3-dev`; the install step picks the GUI lock on Linux
  and the dev lock elsewhere; `--additional-hooks-dir hooks` is passed on Linux only.
- `previewgen/desktop_runtime.py`: the headless fallback is gone. Missing GTK/Qt bindings on
  Linux now log an error and return `1`, and no readiness marker is written.
- `tests/unit/test_desktop_runtime.py`: regression test asserting that a Linux smoke test
  without `gi` fails closed and never writes the marker.
- `.gitignore`: local CI sandbox venvs and the `gui_ready.txt` smoke marker.

## Local evidence (WSL2 Ubuntu, Python 3.12.14, Node 24.15.0)
- Frozen Linux build with the GUI lock + hooks contains 17 typelibs including
  `WebKit2-4.1.typelib` and `Soup-3.0.typelib`.
- Under `xvfb-run`, the app opens a real WebKit window and `DesktopApi.frontend_ready()`
  fires (logged "Frontend mounted and reported ready"), which is what writes the marker now.
- `ruff check .` clean; `pytest tests/ -q` green; frontend typecheck/tests/build green;
  packaged renderer gate 15/15 under `-W error`; frozen `--render-test-all` 9/9 fixtures.

## Not verified here
- Every apt name was checked against the jammy `main`/`universe` Packages index, but the
  build was not run on an actual ubuntu-22.04 runner; PyGObject compiled against this
  machine's girepository headers.
- This is the first time the real `gi` path has executed, and pywebview now logs four
  `Error while processing window.native.<x>: unable to get the value` lines while it
  introspects `DesktopApi`. Cosmetic — the exit code and marker are correct — but it is new
  noise that deserves its own follow-up.
- Bundling the GTK/WebKit stack grows the measured Linux build directory to **574 MB**
  (`du -sh dist/PreviewGen`). Nothing asserts a size ceiling; if that matters it needs an
  explicit check rather than a review comment.
- `pr-checks.yml` and `build.yml` have not executed on this repository since 11:09Z today;
  every run after that is CodeQL, which passes on this branch. None of the evidence above was
  produced by CI, so the first real runner execution can still surface jammy-specific
  problems. If it does, the failure will now be loud: the gate reports the missing binding
  instead of writing its own readiness marker.
