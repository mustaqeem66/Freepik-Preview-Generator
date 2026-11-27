# Linux WebKitGTK blank-screen root cause and fix

**Date:** 2026-11-26  
**Affected release:** `v2.1.3` Linux AppImage  
**Status:** Fixed in source, covered by automated tests, built through the updated Linux CI matrix, and published as `v2.1.4` on 2026-11-27.

## User-visible impact

On Linux Mint 22.3 and other hosts with a newer WebKitGTK than the Ubuntu 22.04 build host, the published AppImage opens a window that stays at the dark application background. The React frontend never mounts, so the application appears permanently blank.

Windows was not affected.

## Root cause

The Linux build froze WebKitGTK's main shared library but did not freeze the matching injected bundle used by `WebKitWebProcess`:

- Frozen: `libwebkit2gtk-4.1.so.0` from the Ubuntu 22.04 build host.
- Frozen: `libjavascriptcoregtk-4.1.so.0` from the Ubuntu 22.04 build host.
- Missing: the matching `libwebkit2gtkinjectedbundle.so`.
- Loaded at runtime: the host distribution's newer `libwebkit2gtkinjectedbundle.so`.

The frozen main library and the host injected bundle therefore used different WebKitGTK ABIs. The renderer aborted in `WKBundleInitialize` before the frontend could mount.

This was not a React, pywebview bridge, GPU, DMABUF, X11, or Wayland defect. Those paths were tested and ruled out during reproduction.

## Reproduction evidence

The published artifact was downloaded from the `v2.1.3` release and verified against the release checksum:

```text
4b929917646facd6d7a3e77f24f52790e16ce9e78f2e8c903cbf24d88afcf8f4  PreviewGen-Linux.AppImage
```

On Linux Mint 22.3 (Ubuntu 24.04 userland):

1. The AppImage process started and loaded its bundled `frontend/dist/index.html`.
2. The frontend ready marker was not written within 75 seconds.
3. The window showed only the `#0F172A` background and its WebView group was inaccessible.
4. The system journal repeatedly recorded a `WebKitWebProcess` crash with this stack:

```text
__GI_abort
libwebkit2gtkinjectedbundle.so
WKBundleInitialize
/tmp/.mount_PreviewGen.../usr/bin/_internal/libwebkit2gtk-4.1.so.0
```

The default, `nodmabuf`, software-rendering, X11, and explicit WebKit-port environment variants all remained not ready.

Artifact inspection confirmed that the AppImage contained the old frozen WebKitGTK and JavaScriptCore libraries but no `libwebkit2gtkinjectedbundle.so`.

## Root-cause proof

The matching Ubuntu 22.04 injected bundle was extracted from:

```text
libwebkit2gtk-4.1-0_2.50.4-0ubuntu0.22.04.1_amd64.deb
```

Pointing the unchanged published AppImage at that bundle with:

```bash
WEBKIT_INJECTED_BUNDLE_PATH=/tmp/opencode/previewgen-audit/matching-injected \
  PREVIEWGEN_READY_MARKER=/tmp/opencode/previewgen-audit/task4-fixed.ready \
  /tmp/opencode/previewgen-audit/PreviewGen-Linux.AppImage --gui-smoke-test
```

produced:

```text
Frontend mounted and reported ready.
```

The process exited `0`, wrote `READY` to the marker, and the journal contained no new `WebKitWebProcess`, `WKBundleInitialize`, or core-dump entries for that run.

This isolated the missing matching bundle as the cause without changing React, the frontend bundle, or the pywebview startup code.

## Implemented fix

### Runtime contract

`previewgen/linux_webkit.py` now:

- leaves source checkouts on the host's matching WebKitGTK installation;
- configures frozen Linux launches to set `WEBKIT_INJECTED_BUNDLE_PATH` before pywebview creates the window;
- points the variable at `<PyInstaller resource root>/webkit_injected_bundle`;
- fails closed with a diagnostic error when the frozen injected bundle is absent.

`previewgen/desktop_runtime.py` applies this configuration before `webview.create_window`, so no misleading blank window can be created with an incompatible runtime.

### Packaging contract

`hooks/hook-gi.repository.WebKit2.py` now discovers the injected bundle from the same selected WebKitGTK package and freezes it in `webkit_injected_bundle/`. It also records a `webkit_manifest.json` provenance record beside the bundle. The manifest names the selected API and Debian package version, and records SHA-256 checksums for the exact build-host WebKitGTK library and injected bundle. The verifier recomputes both packaged checksums and requires the injected bundle's ELF `DT_NEEDED` list to name the same frozen library, so a 4.0/4.1 mix or a substituted file fails closed.

Ubuntu 22.04 and 24.04 install the file at this path relative to the selected shared-library directory:

```text
webkit2gtk-4.1/injected-bundle/libwebkit2gtkinjectedbundle.so
```

The hook checks that versioned package layout first and retains the direct-directory fallback for other layouts. On the local Linux Mint 22.3 host, the real hook resolved:

```text
/lib/x86_64-linux-gnu/webkit2gtk-4.1/injected-bundle/libwebkit2gtkinjectedbundle.so
```

### Frozen bootstrap compatibility

The local onedir rebuild also exposed a separate PyInstaller bootstrap defect before PreviewGen could start. Setuptools 84.2.1 exposes `pkg_resources.extern.jaraco` through vendored modules, but PyInstaller 6.22.3 did not collect those modules in the Linux build:

```text
ImportError: The 'jaraco' package is required; normally this is bundled with this package
```

This was not related to WebKitGTK, but it would prevent CI from producing a testable replacement artifact. The Linux build now uses `--collect-all setuptools`, and a structural CI test prevents that collection rule from disappearing. The corrected frozen application contained 339 collected Setuptools files, including 12 vendored `jaraco` files, and started normally, which verifies that the collection rule resolves the bootstrap failure.

### Frozen renderer compatibility

The fresh native build also exposed an independent release-renderer failure. The host's system Pillow 10.2.0 shadowed the virtual environment during the first build and does not expose `ImageMath.lambda_eval`, while the pinned `psd-tools` release calls that API when compositing PSD previews:

```text
AttributeError: module 'PIL.ImageMath' has no attribute 'lambda_eval'
```

The secure and compatible resolution is Pillow 13.0.0: it fixes the published decoder advisories and still provides the `ImageMath.lambda_eval` API used by `psd-tools` 1.25.0. All three hash-pinned Python lock files now select Pillow 13.0.0, and a structural regression test keeps the patched floor and major-version ceiling in place. A clean isolated install of the updated runtime lock selected Pillow 13.0.0, exposed `ImageMath.lambda_eval`, rendered `sample.psd` successfully, and passed the advisory audit with no known vulnerabilities.

### Release gate

`scripts/verify_linux_webkit_bundle.py` accepts a PyInstaller onedir directory or an AppImage. It requires:

- a frozen WebKitGTK 4.1 or 4.0 shared library;
- `libwebkit2gtkinjectedbundle.so` in the required `webkit_injected_bundle/` directory;
- a valid `webkit_manifest.json` with package, API, and checksum provenance; and
- matching packaged library and injected-bundle checksums with a consistent ELF dependency declaration.

The Linux build job runs this verifier both before AppImage creation and against the final downloadable `PreviewGen-Linux.AppImage`. The clean-machine Linux matrix runs the artifact on both Ubuntu 22.04 and Ubuntu 24.04 and requires the Ubuntu 24.04 host package to be genuinely newer than the recorded build-host package. Ubuntu 22.04 exercises the frozen artifact through Xvfb, explicit X11, and headless Wayland sessions. Ubuntu 24.04 verifies the newer-host package ordering, provenance manifest, packaged renderer, and artifact contents; its headless Mesa 25 stack cannot initialize an EGL display for the older frozen WebKitGTK 2.50 pair, so the real Ubuntu 24.04 GUI path is covered by the native Linux Mint 22.3 evidence below.

The verifier rejects the known-bad `v2.1.3` AppImage:

```text
FATAL: Packaged artifact is missing libwebkit2gtkinjectedbundle.so in the required webkit_injected_bundle/ directory
verifier_exit=1
```

## Regression coverage

Automated tests now cover:

- frozen Linux runtime selection of the packaged injected bundle;
- fail-closed behavior when the frozen injected bundle is missing;
- source-checkout pass-through without changing the host WebKit environment;
- fail-closed desktop startup before window creation;
- PyInstaller hook discovery from the real Ubuntu package layout;
- packaged verifier rejection of a missing injected bundle or provenance manifest;
- packaged verifier rejection of library or injected-bundle checksum mismatches;
- packaged verifier acceptance and extraction-failure coverage for AppImages;
- hook discovery from versioned 4.1 and 4.0 layouts plus the direct-directory fallback;
- CI invocation of the packaged verifier against both the onedir and final AppImage;
- clean-machine coverage on Ubuntu 22.04 and Ubuntu 24.04 with enforced newer-host package ordering;
- explicit Xvfb, X11, and Wayland packaged GUI scenarios on the Ubuntu 22.04 build-compatible host, with renderer-crash checks;
- Linux packaging collection of Setuptools' vendored `pkg_resources` modules;
- a Pillow compatibility ceiling that preserves PSD compositing.

## Verification evidence

- Focused WebKitGTK, verifier, CI, and desktop-runtime regression suite: `44 passed`.
- Final full Python suite after the review fix pass: `689 passed, 5 skipped`.
- Frontend typecheck: passed.
- Frontend Vitest suite: `34 files passed`, `194 tests passed`.
- Frontend production build: passed.
- Ruff over the repository: passed.
- Pyrefly over the repository: `0 errors` (2 suppressed, 15 warnings not shown at the default severity).
- Dependency-lock structural verification: passed.
- Published `v2.1.3` AppImage with the matching Ubuntu 22.04 bundle override: exit `0`, `READY` marker written, no renderer crash in the journal.
- New release verifier against the published `v2.1.3` AppImage: exit `1` with the expected missing-bundle diagnostic.
- Corrected PyInstaller onedir: verifier passed; the packaged tree contained `libwebkit2gtk-4.1.so.0`, `webkit_injected_bundle/libwebkit2gtkinjectedbundle.so`, and `webkit_manifest.json`.
- Corrected onedir dependency inspection: embedded `PIL._version` reported Pillow `13.0.0`.
- Corrected onedir packaged PSD render: `sample.psd` produced a valid 220×160 RGB JPEG with 2,252 distinct colors and 16,278 bytes.
- Corrected onedir native X11 GUI smoke test with `WEBKIT_INJECTED_BUNDLE_PATH` explicitly unset: exit `0`, `READY` marker written, and `Frontend mounted and reported ready.` in the application log.
- The `v2.1.4` tag workflow built all platform artifacts and passed the Ubuntu 22.04, Ubuntu 24.04, Windows, and macOS clean-machine jobs.
- Published `v2.1.4` Linux artifact: `PreviewGen-Linux.AppImage`, SHA-256 `76348d54d52951d26fb9d9b54bffd4f793bede5d5c4d53995cfee5dd7824bf54`.
- The downloaded `v2.1.4` AppImage matched `SHA256SUMS.txt` and passed `scripts/verify_linux_webkit_bundle.py`, including the matching injected bundle and provenance manifest.
- The release is published at `https://github.com/mustaqeem66/Freepik-Preview-Generator/releases/tag/v2.1.4` and is marked as the latest release.
- Journal checks after the corrected native X11 onedir and AppImage runs found zero `WKBundleInitialize`, `libwebkit2gtkinjectedbundle`, or `WebKitWebProcess` crash entries.

## Release outcome and remaining risk

The corrected release was published as `v2.1.4` on 2026-11-27. Its tag workflow built the platform artifacts, passed the clean-machine matrix, verified the final AppImage, and created the release assets. The published Linux checksum and the provenance verifier were independently checked after download.

The remaining limitation is headless CI compatibility: Ubuntu 24.04's Mesa 25 EGL stack cannot create a display for the Ubuntu 22.04-frozen WebKitGTK 2.50 pair. The artifact therefore uses the full Xvfb/X11/Wayland GUI gate on Ubuntu 22.04, while Ubuntu 24.04 verifies newer-host ordering, provenance, rendering, and artifact contents. Native Linux Mint 22.3 evidence covers the real Ubuntu 24.04 GUI path. Passing Ubuntu 22.04 and 24.04 does not certify every Linux distribution; the README states that limitation explicitly.
