# macOS Startup and Packaging Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make macOS startup failures visible and clean, and make the final macOS artifact prove its bundle contents and rendered frontend before release acceptance.

**Architecture:** Keep the current `file://` WKWebView transport, but put all native setup under one error boundary and add an explicit DOM-render verdict. Add a platform-neutral macOS bundle verifier and invoke it on both the built `.app` and the app mounted from the final DMG. Register renderer child PIDs with the existing lifecycle registry so shutdown can terminate spawned work.

**Tech Stack:** Python 3.12, pywebview 6.2.1/Cocoa, PyInstaller 6.22.3, React 19/TypeScript, pytest, Vitest, GitHub Actions macOS runners.

**Spec:** `docs/superpowers/specs/2026-11-27-macos-startup-audit-design.md`

## Global Constraints

- Do not mutate the published `v2.1.4` release assets.
- Do not change the Linux WebKitGTK runtime contract.
- Do not broaden the production CSP or weaken `ALLOW_FILE_URLS` security settings without native evidence.
- Linux-only tests cannot prove macOS GUI behavior; macOS CI must remain the final authority.
- The current `file://` WKWebView transport stays in place for this change.

## Review Focus

- A missing `stderr` in a frozen windowed process must not hide the original startup failure.
- A missing frontend bundle must not leave a bound preview socket, thread, or temp directory.
- A preview-server bind failure must produce a native diagnostic and a nonzero exit, not an uncaught exception.
- A renderer that starts during shutdown must be registered before the GUI can tear it down.
- A packaged `.app` with a correct executable but missing frontend, `Info.plist`, pywebview JS, or frozen Setuptools content must fail verification.

---

### Task 1: Put macOS native startup under one fail-closed error boundary

**Files:**
- Modify: `previewgen/desktop_runtime.py`
- Modify: `previewgen/entrypoint.py`
- Modify: `previewgen/settings.py`
- Test: `tests/unit/test_desktop_runtime.py`
- Test: `tests/unit/test_startup_responsiveness.py`

**Interfaces:**
- Produces: `start_desktop_app() -> int` returns `1` on setup failure, shows `show_fatal_error(...)`, and cleans partially created resources.
- Produces: `show_fatal_error(title: str, message: str) -> None` never raises when `sys.stderr` is absent.
- Produces: `previewgen.entrypoint.main() -> int` continues when persistent log setup fails.

- [ ] **Step 1: Write failing startup-boundary tests**

Add tests that force `DesktopApi()` and `webview.create_window()` to raise, force `create_window()` to return `None`, remove the frontend bundle, and set `sys.stderr = None`. Assert a nonzero result, one fatal diagnostic, and `api.cleanup()` for every partially created API.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest tests/unit/test_desktop_runtime.py tests/unit/test_startup_responsiveness.py -q`

Expected: new tests fail because setup exceptions escape, the missing-bundle path skips cleanup, the stderr fallback raises, and log setup is fatal.

- [ ] **Step 3: Implement the minimal startup boundary**

Move `import webview` into `start_desktop_app()`. Construct the API only after the frontend bundle is validated. Wrap API construction and `webview.create_window()` in the same guarded setup path as `webview.start()`. In the failure path, call `api.cleanup()` when an API exists, show the fatal dialog, return `1`, and do not re-raise.

Make `show_fatal_error()` write to `sys.stderr` only when it is present and writable. In `entrypoint.main()`, catch log-configuration failure, install a minimal in-memory logging fallback, and continue to CLI or GUI dispatch.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pytest tests/unit/test_desktop_runtime.py tests/unit/test_startup_responsiveness.py -q`

Expected: PASS with no warnings.

- [ ] **Step 5: Commit the startup-boundary change**

```bash
git add previewgen/desktop_runtime.py previewgen/entrypoint.py previewgen/settings.py tests/unit/test_desktop_runtime.py tests/unit/test_startup_responsiveness.py
git commit -m "fix(macos): fail visibly during native startup"
```

### Task 2: Register renderer processes with lifecycle shutdown

**Files:**
- Modify: `previewgen/lifecycle.py`
- Modify: `previewgen/batch/runner.py`
- Modify: `previewgen/renderer_process.py`
- Test: `tests/unit/test_shutdown_lifecycle.py`
- Test: `tests/unit/test_process_tree.py`

**Interfaces:**
- Consumes: `process_folder(..., on_process_started: Callable[[int], None] | None = None)`.
- Produces: `RendererProcessPool.render(..., on_process_started: Callable[[int], None] | None = None)`.
- Produces: the batch `ActiveOperation.process_ids` contains every renderer PID as it starts.

- [ ] **Step 1: Write failing renderer-registration tests**

Add a test that starts a controlled renderer child, records its PID through the new callback, registers a lifecycle operation, invokes `LifecycleManager.cleanup()`, and asserts the child and descendants are dead and the render temp directory is gone.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pytest tests/unit/test_shutdown_lifecycle.py::test_cleanup_terminates_registered_batch_renderer -q`

Expected: FAIL because `process_ids` remains empty and the callback does not exist.

- [ ] **Step 3: Implement PID propagation and tree termination**

Add the optional callback to the renderer pool and call it immediately after `mp.Process.start()`. Thread the callback through `process_folder` and `LifecycleManager.start_batch` into the active batch operation. During cleanup, call `previewgen.proc.terminate_process_tree(pid)` instead of signalling only the direct PID, then verify survivors.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pytest tests/unit/test_shutdown_lifecycle.py tests/unit/test_process_tree.py -q`

Expected: PASS.

- [ ] **Step 5: Commit renderer lifecycle tracking**

```bash
git add previewgen/lifecycle.py previewgen/batch/runner.py previewgen/renderer_process.py tests/unit/test_shutdown_lifecycle.py tests/unit/test_process_tree.py
git commit -m "fix(macos): terminate spawned renderers on shutdown"
```

### Task 3: Add a fail-closed macOS `.app` bundle verifier

**Files:**
- Create: `scripts/verify_macos_bundle.py`
- Create: `tests/unit/test_verify_macos_bundle.py`

**Interfaces:**
- Produces: `python scripts/verify_macos_bundle.py <PreviewGen.app>` exits `0` only for a complete bundle and `1` with a specific diagnostic otherwise.
- Produces: `verify_bundle(app_path: Path, expected_version: str = "2.1.4") -> list[str]` for unit testing.

- [ ] **Step 1: Write failing verifier tests**

Build a minimal valid fake `.app` fixture with `Info.plist`, executable, frontend HTML and referenced assets, settings schema, pywebview JS, Setuptools vendored content, and Cocoa module markers. Parameterize one missing item at a time and assert a specific failure. Add an acceptance test for the valid fixture.

- [ ] **Step 2: Run the verifier tests and verify RED**

Run: `pytest tests/unit/test_verify_macos_bundle.py -q`

Expected: import failure because the verifier does not exist.

- [ ] **Step 3: Implement the verifier**

Read `Contents/Info.plist` with `plistlib`. Require:

- `CFBundleIdentifier == "com.zenartisan.previewgen"`;
- `CFBundleExecutable == "PreviewGen"`;
- `CFBundleShortVersionString == expected_version`;
- `Contents/MacOS/PreviewGen` exists and starts with a Mach-O magic value;
- `Contents/Frameworks/frontend/dist/index.html` exists and all local script/style/font references exist;
- `Contents/Frameworks/previewgen/settings_schema.json` exists;
- `Contents/Frameworks/webview/js/api.js` and `finish.js` exist;
- frozen `pkg_resources` contains the vendored `jaraco` marker;
- `objc`, `Foundation`, `AppKit`, and `WebKit` modules are present under `Contents/Frameworks`.

Use `lipo -archs` when available and require the runner architecture. Return all failures instead of stopping at the first.

- [ ] **Step 4: Run the verifier tests and verify GREEN**

Run: `pytest tests/unit/test_verify_macos_bundle.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the bundle verifier**

```bash
git add scripts/verify_macos_bundle.py tests/unit/test_verify_macos_bundle.py
git commit -m "feat(macos): verify packaged app resources"
```

### Task 4: Prove the native frontend rendered meaningful DOM

**Files:**
- Modify: `previewgen/api.py`
- Test: `tests/unit/test_readiness_assessment.py`
- Test: `tests/unit/test_csp_packaged_probe.py`

**Interfaces:**
- Produces: `PREVIEWGEN_RENDER_MARKER` names a JSON file containing `{"ok": bool, "rootChildCount": int, "rootWidth": number, "rootHeight": number, "textLength": int, "error": str | null}`.
- Produces: `frontend_ready()` writes the render marker after React mounts.

- [ ] **Step 1: Write failing render-evidence tests**

Mock a WebView evaluation that returns a valid root with children, width, height, and text; assert the marker is `ok: true`. Parameterize an empty root, zero dimensions, empty text, evaluation error, and timeout; assert `ok: false` with a stable error code. Assert the normal ready marker is still written.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest tests/unit/test_readiness_assessment.py tests/unit/test_csp_packaged_probe.py -q`

Expected: FAIL because no render marker is written.

- [ ] **Step 3: Implement bounded DOM evidence collection**

After `frontend_ready()` writes the existing ready marker, evaluate a bounded JSON expression in the live WebView. Require `rootChildCount > 0`, `rootWidth > 0`, `rootHeight > 0`, and `textLength > 0`. Write the render marker even when the check fails so CI can publish the reason. Reuse `_evaluate_js_bounded()` with a separate five-second timeout.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `pytest tests/unit/test_readiness_assessment.py tests/unit/test_csp_packaged_probe.py -q`

Expected: PASS.

- [ ] **Step 5: Commit render evidence**

```bash
git add previewgen/api.py tests/unit/test_readiness_assessment.py tests/unit/test_csp_packaged_probe.py
git commit -m "feat(macos): record native render readiness"
```

### Task 5: Harden the macOS build and final-DMG release gates

**Files:**
- Modify: `.github/workflows/build.yml`
- Modify: `tests/unit/test_ci_workflow_config.py`

**Interfaces:**
- Consumes: `scripts/verify_macos_bundle.py <app-path>`.
- Consumes: `PREVIEWGEN_READY_MARKER`, `PREVIEWGEN_RENDER_MARKER`, `PREVIEWGEN_CSP_MARKER`, and `PREVIEWGEN_CSP_VIOLATIONS`.

- [ ] **Step 1: Write failing workflow-contract tests**

Assert that:

- the PyInstaller command collects Setuptools unconditionally;
- the macOS build runs the bundle verifier against `dist/PreviewGen.app`;
- the macOS build job runs `--gui-smoke-test` with ready, render, and CSP markers;
- the clean-machine job runs the bundle verifier against the mounted final DMG app;
- the clean-machine job requires the render marker to contain `ok: true`, non-zero root dimensions, and non-empty text;
- the evidence upload includes `gui_ready.txt`, `render_ready.json`, the macOS application log, and the CSP markers.

- [ ] **Step 2: Run the workflow tests and verify RED**

Run: `pytest tests/unit/test_ci_workflow_config.py -q`

Expected: new assertions fail against the current workflow.

- [ ] **Step 3: Implement the workflow gates**

Collect Setuptools on every platform. Keep the headless `--smoke-test` under a processor-smoke name. Add a macOS GUI smoke step in the build job with bounded output capture and marker assertions. Run the bundle verifier after the `.app` is created and again in the clean-machine job after mounting the final DMG. Copy `~/Library/Logs/PreviewGen/previewgen.log` into the evidence directory under `if: always()`.

- [ ] **Step 4: Run the workflow tests and verify GREEN**

Run: `pytest tests/unit/test_ci_workflow_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the release-gate change**

```bash
git add .github/workflows/build.yml tests/unit/test_ci_workflow_config.py
git commit -m "ci(macos): gate packaged startup and render evidence"
```

### Task 6: Verify the complete branch and document the audit

**Files:**
- Create: `docs/engineering/2026-11-27-macos-startup-audit.md`
- Modify: `docs/superpowers/specs/2026-11-27-macos-startup-audit-design.md`
- Keep: `docs/diagrams/macos-startup-flow.html`
- Keep: `floorplan/` ignored and uncommitted

**Interfaces:**
- Produces: an engineering record that separates confirmed defects, native-only hypotheses, test evidence, and remaining macOS limitations.

- [ ] **Step 1: Run all focused regression suites**

Run:

```bash
pytest tests/unit/test_desktop_runtime.py tests/unit/test_startup_responsiveness.py \
  tests/unit/test_shutdown_lifecycle.py tests/unit/test_process_tree.py \
  tests/unit/test_verify_macos_bundle.py tests/unit/test_readiness_assessment.py \
  tests/unit/test_csp_packaged_probe.py tests/unit/test_ci_workflow_config.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full Python and frontend suites**

Run:

```bash
python -m pytest tests/ -q
python -m ruff check .
python -m pyrefly check
cd frontend && npm run typecheck && npm test && npm run build
```

Expected: all commands exit `0` with no new warnings.

- [ ] **Step 3: Record the evidence and limitations**

Document the confirmed startup defects, the packaging gates, the exact commands and results, the macOS CI run URL, the fact that Linux cannot prove WKWebView behavior, and the remaining visible-screenshot, Intel/universal2, installed-app, and navigation-lockdown gaps.

- [ ] **Step 4: Rebuild the floorplan and validate the diagram**

Run:

```bash
node /home/must/.agents/skills/floorplan/scripts/build.mjs .
python3 /home/must/.agents/skills/diagram-design/scripts/self_check.py docs/diagrams/macos-startup-flow.html
python3 /home/must/.agents/skills/diagram-design/scripts/verify_geometry.py docs/diagrams/macos-startup-flow.html
```

Expected: floorplan reports 100% descriptions and no important health findings; both diagram checks report no findings.

- [ ] **Step 5: Commit the audit record**

```bash
git add docs/engineering/2026-11-27-macos-startup-audit.md docs/superpowers/specs/2026-11-27-macos-startup-audit-design.md docs/diagrams/macos-startup-flow.html
git commit -m "docs(macos): record startup and packaging audit"
```
