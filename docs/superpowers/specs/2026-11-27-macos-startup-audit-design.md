# macOS startup and packaging hardening design

**Date:** 2026-11-27  
**Implementation status:** Source implementation and Linux-hosted regression verification are complete. Native macOS build and final-DMG CI acceptance remain required before merge and release promotion. See `docs/engineering/2026-11-27-macos-startup-audit.md`.

## Intent

Make the macOS packaged app fail visibly instead of silently when Cocoa, bundled resources, or the native window cannot start. Make the release pipeline prove that the final `.app` contains the resources WKWebView needs and that the frontend rendered meaningful DOM before a DMG is accepted.

## Confirmed evidence

- `previewgen.desktop_runtime.py` imports `webview` and constructs `DesktopApi`, resolves the bundle, and creates the window before the existing error boundary around `webview.start()`.
- A missing frontend bundle returns before `api.cleanup()`, leaving the eagerly bound preview HTTP server alive.
- The macOS build job's “Startup Test” invokes `--smoke-test`, which is explicitly headless and never opens WKWebView.
- CI collects Setuptools only on Linux even though the committed spec collects it for every platform and the frozen bootstrap can require Setuptools' vendored modules.
- The macOS package step checks only that `.app` and its executable exist. It does not verify `Info.plist`, bundle identity/version, the packaged frontend tree, pywebview JavaScript, settings schema, or frozen Setuptools content.
- The pinned pywebview Cocoa backend loads `file://` through `NSURLRequest` and has no provisional-navigation failure handler. The current v2.1.4 package mounted successfully in WKWebView, so this is a diagnostic risk, not a proven current blank-screen cause.
- The Cocoa backend does not emit pywebview's `navigating` event, so the application's claimed navigation lockdown is not active there.
- `ActiveOperation.process_ids` is never populated by renderer processes.

## Approaches considered

### 1. Diagnostics only

Add logs and macOS CI checks while leaving runtime behavior unchanged.

Trade-off: smallest risk, but known startup exceptions still terminate a windowed app without a user-visible diagnostic and known cleanup leaks remain.

### 2. Harden confirmed startup and packaging defects (selected)

Move native imports and setup under a controlled error boundary; guarantee cleanup; register renderer PIDs; collect frozen dependencies consistently; verify the `.app`; run a real WKWebView/DOM smoke test; and publish the macOS evidence.

Trade-off: touches shared startup and release code, but every production behavior change has a failing regression test and native CI remains the final authority.

### 3. Serve the frontend over loopback HTTP on macOS

Replace the `file://` document with a token-protected local HTTP origin.

Trade-off: removes file-origin/module/CSP ambiguity, but the current macOS release already mounts from `file://`. This would be a speculative transport change without a native failing reproduction, so it is deferred.

## Design

### Startup boundary

- Import `webview` inside `start_desktop_app()` so an omitted or damaged PyObjC/WebKit package reaches the fatal-error handler.
- Wrap API construction, resource lookup, and window creation in one guarded setup path.
- On every failure, show the native macOS diagnostic, return a nonzero exit code, and run cleanup for partially created resources.
- Make the fatal-error fallback safe when a frozen windowed process has no `stderr`.
- Treat log-directory creation as best effort. A logging failure must not prevent the GUI from starting.

### Resource and shutdown correctness

- Resolve and validate the frontend bundle before creating the API where practical, so a missing bundle cannot start the preview server.
- Keep preview-server cleanup idempotent and call it on all failed-start paths.
- Populate the active batch operation's `process_ids` when a renderer child starts, so macOS shutdown can terminate a spawned renderer and its descendants.

### Packaged macOS verification

Add `scripts/verify_macos_bundle.py` to require:

- a valid `.app` layout;
- `Info.plist` values for bundle identifier, executable, and app version;
- the frozen frontend `index.html`, every local script/style/font it references, and the settings schema;
- pywebview's injected JavaScript;
- frozen Setuptools content needed by the bootstrap;
- required Cocoa/PyObjC modules;
- an executable Mach-O whose architecture matches the build runner.

The build job must run the verifier against the `.app`. The clean-machine job must run it against the app mounted from the final DMG.

### Native GUI acceptance

- Keep the hidden `--gui-smoke-test` for deterministic startup and CSP checks.
- Add a render-evidence marker written from the frontend handshake that records meaningful React root content and non-zero dimensions.
- Require both the frontend-ready marker and render-evidence marker in the macOS packaged gate.
- Rename the current build step so it no longer calls a headless processor check a macOS GUI startup test.
- Upload the macOS ready marker, render evidence, CSP evidence, and application log even on failure.

### Frozen dependency collection

Collect Setuptools on every PyInstaller target, not only Linux. This removes a known bootstrap omission without changing the locked dependency versions.

## Constraints

- Do not mutate the published `v2.1.4` release assets.
- Do not claim native macOS behavior from Linux-only tests.
- Keep the WebKitGTK Linux contract unchanged.
- Do not broaden the production CSP or weaken `ALLOW_FILE_URLS` security settings without native evidence.
- A real visible screenshot and universal/Intel macOS support remain separate follow-up work; this change does not claim those guarantees.

## Acceptance

- Focused regression tests fail before implementation and pass afterward.
- Python, frontend, lint, type, and structural CI checks pass.
- The macOS build produces a verified `.app`, reaches frontend-ready and render-evidence markers in WKWebView, and passes the packaged CSP check.
- The final DMG's mounted app passes the same bundle, render, CSP, and renderer gates.
- No new macOS CI warning is treated as evidence of success without a corresponding assertion.
