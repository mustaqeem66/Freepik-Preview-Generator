# macOS startup and packaging audit

**Date:** 2026-11-27  
**Affected platform:** macOS 11+ (native arm64 release runner)  
**Related release:** `v2.1.5` is the published native-verified baseline; the final post-publication corrections are published as `v2.1.6`.
**Status:** Fixed in source and natively verified. `v2.1.5` remains unchanged; `v2.1.6` is published as the latest release.

## Scope

PreviewGen's macOS desktop path was reviewed from the frozen Python entrypoint through the pywebview Cocoa/WKWebView window, the React bundle, the native bridge, isolated renderer children, the preview HTTP service, shutdown, PyInstaller packaging, signing, DMG creation, and clean-machine acceptance.

The Linux WebKitGTK injected-bundle fix does not transfer to macOS. macOS uses Apple's WKWebView through pywebview's Cocoa backend. The published `v2.1.4` DMG also proves that the current `file://` frontend mounted in WKWebView on the macOS 26 arm64 runner.

## Confirmed defects and fixes

### Native startup errors escaped the user-visible failure path

`previewgen.desktop_runtime.py` imported `webview`, constructed `DesktopApi`, resolved the frontend bundle, and created the native window before the error boundary around `webview.start()`. A damaged frozen PyObjC/WebKit package, a preview-server bind failure, or a Cocoa window-construction error could therefore terminate a windowed `.app` without the intended `osascript` diagnostic.

The native import and setup now run inside one fail-closed boundary. Setup failures:

- show a native fatal diagnostic;
- return exit code `1`;
- clean up a partially created API, preview socket, HTTP thread, and temp directory; and
- never replace the original error with a missing-`stderr` failure.

Persistent log setup is now best effort. A read-only or full home directory no longer prevents the GUI from starting.

### A missing frontend bundle started unnecessary services

`DesktopApi()` eagerly binds the loopback preview server. The old code created that API before checking whether `frontend/dist/index.html` existed. A missing bundle returned an error but left the server and its temp directory alive until process teardown.

The frontend bundle is now validated before the API is constructed.

### Spawned renderers were not registered with shutdown

`ActiveOperation.process_ids` existed but no renderer PID was ever added. On macOS, renderer children use Python's `spawn` model. If the GUI shut down while a renderer was active, the lifecycle registry could not terminate it.

Renderer PIDs now flow from `RendererProcessPool` through the batch runner into the active lifecycle operation. Shutdown terminates the complete process tree and reports survivors.

### Frozen Setuptools collection was Linux-only

The frozen bootstrap had already failed on Linux because Setuptools' vendored `jaraco` modules were not collected. CI nevertheless limited `--collect-all setuptools` to Linux while the committed spec collected it everywhere.

The collection rule now applies to every PyInstaller target.

### The macOS build step did not test WKWebView

The build job's step named “macOS Startup Test” ran `--smoke-test`, which is a headless processor check and never creates a window. The final DMG's clean-machine job did run `--gui-smoke-test`, but the build itself could package and sign an app that never opened.

The build now runs a real packaged WKWebView smoke with separate ready, render, and CSP markers. The final DMG's mounted app repeats those checks.

### The macOS app had no structural release gate

The package step checked only that `PreviewGen.app` and its executable existed. A missing frontend asset, bridge script, settings file, native WebKit module, frozen dependency, or correct bundle version could survive packaging.

`scripts/verify_macos_bundle.py` now requires:

- a valid `Contents/Info.plist`;
- bundle identifier `com.zenartisan.previewgen`;
- executable name `PreviewGen`;
- `CFBundleShortVersionString` and `CFBundleVersion` matching the source version;
- a Mach-O executable whose architecture includes the build runner;
- `frontend/dist/index.html` and every local script/style/image it references;
- `previewgen/settings_schema.json`;
- pywebview's `api.js` and `finish.js`;
- frozen Setuptools `jaraco` content;
- native `objc`, Foundation, AppKit, and WebKit modules.

The workflow writes the source version into `Info.plist` before verification and signing.

### “Frontend ready” did not prove a rendered interface

The native ready marker proved that React mounted and called the bridge. It did not prove that the root contained visible content.

The native handshake now writes `PREVIEWGEN_RENDER_MARKER` with:

- `rootChildCount`;
- root width and height;
- body text length; and
- a stable failure code.

`scripts/check_render_marker.py` accepts only a non-empty root with non-zero dimensions and text.

## Regression coverage

Automated tests now cover:

- API construction failure with a visible diagnostic and nonzero exit;
- missing frontend bundle before API construction;
- window-construction failure and a missing window object with cleanup;
- fatal-error output when a frozen process has no `stderr`;
- persistent logging failure not blocking startup;
- renderer PID registration, completion removal, late-start termination, and process-tree cleanup;
- transactional desktop API initialization with no orphaned preview service;
- complete and deliberately broken macOS app bundles;
- valid, empty, timed-out, malformed, and missing render evidence;
- unconditional frozen Setuptools collection;
- build-time and final-DMG macOS bundle verification;
- build-time and final-DMG WKWebView render evidence; and
- upload of macOS ready, render, CSP, captured GUI output, and application-log evidence;
- bounded GUI smoke timeout that terminates the complete app process group.

## Verification evidence

- Focused macOS/startup/package regression suite: `106 passed, 2 skipped`.
- Full Python suite: `739 passed, 5 skipped`.
- Ruff: passed.
- Pyrefly: `0 errors` (2 suppressed, 18 warnings below the default severity).
- Frontend typecheck: passed.
- Frontend Vitest suite: `34 files passed`, `194 tests passed`.
- Frontend production build: passed.
- Floorplan: `273/273` files described, `0` unassigned, `0` important health findings.
- Diagram self-check: passed.
- Diagram geometry check: passed with `0` findings.

The published `v2.1.4` DMG was downloaded and extracted for comparison. With only its incorrect `Info.plist` version normalized to `2.1.4`, the new bundle verifier accepts the published app, proving that its current frontend, pywebview JavaScript, frozen Setuptools content, and native Cocoa modules satisfy the structural contract. Before normalization, the verifier fails closed on the published `0.0.0` bundle version.

## Native and publication evidence

The `v2.1.5` tag workflow built every platform and passed all four clean-machine jobs:

- tag workflow: https://github.com/mustaqeem66/Freepik-Preview-Generator/actions/runs/46044582066
- Windows build and clean-machine job: passed
- macOS `.app`/DMG build and clean-machine job: passed
- Ubuntu 22.04 build and clean-machine job: passed
- Ubuntu 24.04 clean-machine job: passed

The native macOS jobs proved that:

1. the built `.app` passed `scripts/verify_macos_bundle.py`;
2. the packaged app wrote the ready marker;
3. the packaged app wrote render evidence with `ok: true`;
4. the packaged WKWebView passed the CSP/preview probe;
5. the app mounted from the final DMG passed the same checks; and
6. every renderer fixture still rendered through the frozen app.

The release is published at https://github.com/mustaqeem66/Freepik-Preview-Generator/releases/tag/v2.1.5 and is marked as the latest release. Published asset digests are:

- `PreviewGen-macOS.dmg`: `cea57cd592746a6845b4a7bb9491c8a263b7526a99286c4671b525591bf95e58`
- `PreviewGen-Linux.AppImage`: `ea572efa664d254a27b8bfddf768682516ebe9f154ecfc5985ee452a097bbadd`
- `PreviewGen-Setup.exe`: `d7690a3919e8d3ba70771847863477020559471a6a3ae0ffaeb5928f25cbf6aa`
- `PreviewGen-Windows.zip`: `ca8a682f3b1a3c1e18dfd7b3796f0fb8411ff9953bb3a42e0a6939c8409501f5`

## Post-publication audit correction

An independent final review after `v2.1.5` publication found two additional lifecycle gaps and one diagnostic gap:

- a failed macOS `osascript` dialog could suppress the stderr fallback for a fatal startup error;
- single-export renderer and asset-probe workers were not registered with shutdown; and
- late operation registration and surviving renderer descendants could escape lifecycle accounting.

PR #199 fixes these paths and adds regression coverage. The published `v2.1.5` assets are not modified. The corrections ship in `v2.1.6`:

- https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/199
- complete Python suite: `746 passed, 5 skipped`
- focused runtime/lifecycle suite: `36 passed`
- independent final review: no Critical or Important findings

### `v2.1.6` publication evidence

The `v2.1.6` tag workflow built every platform and passed all four clean-machine jobs:

- tag workflow: https://github.com/mustaqeem66/Freepik-Preview-Generator/actions/runs/46115031330
- Windows build and clean-machine job: passed
- macOS `.app`/DMG build and clean-machine job: passed
- Ubuntu 22.04 build and clean-machine job: passed
- Ubuntu 24.04 clean-machine job: passed
- release artifact and checksum job: passed

The release is published and marked as the latest release at https://github.com/mustaqeem66/Freepik-Preview-Generator/releases/tag/v2.1.6. Published asset digests are:

- `PreviewGen-macOS.dmg`: `b83b993d9f8fd7d7765208b50d0f21ff5d79bcb2d1cfe5e673462feaaa957afe`
- `PreviewGen-Linux.AppImage`: `053035e6e72cfb638bf0b4e29157635fe7914c8596d002edb0e234d905eae5ae`
- `PreviewGen-Setup.exe`: `9f5d9036f68ce5750080ffa9e09f8139c40d42cb57aab369948486876bec25a8`
- `PreviewGen-Windows.zip`: `d75437b75f949c4af1f920278eb1ac6fd8226cc218dce8bea021684acf9179ee`
- `SHA256SUMS.txt`: `9207776adac612b90c106ae4e0569e89a7277f41168c668c9623ae2877604913`

The published `SHA256SUMS.txt` was downloaded independently, and its digest and four listed artifact digests matched the GitHub release metadata. The published macOS DMG was also downloaded, extracted, and accepted by `scripts/verify_macos_bundle.py`.

## Remaining macOS limitations

These are confirmed gaps or native-only risks not changed by this work:

- pywebview 6.2.1's Cocoa backend loads a `file://` URL with a generic request and does not expose provisional-navigation failure events. The current release mounts successfully, but a future WebKit/package-location failure should be diagnosed through the new render marker and macOS log rather than inferred from a blank window.
- pywebview's Cocoa backend does not emit the application's `navigating` event. The claimed navigation lockdown is therefore not active on macOS. The current frontend contains no external links, but a platform-native navigation policy remains follow-up work.
- The release is built and tested on arm64 only. Intel and universal macOS support remain separate release work.
- The clean-machine job executes the app from a mounted DMG. It does not yet prove a copied `/Applications` install, Dock/LaunchServices activation, or Gatekeeper acceptance of a quarantined download.
- The render evidence proves meaningful DOM and dimensions, not a pixel-perfect visible screenshot.
- macOS has no enforced per-child renderer memory ceiling. The existing timeout and process-tree cleanup remain the available containment mechanism.
