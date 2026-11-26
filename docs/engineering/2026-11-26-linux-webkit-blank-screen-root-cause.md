# Linux WebKitGTK blank-screen root cause and fix

**Date:** 2026-11-26  
**Affected release:** `v2.1.3` Linux AppImage  
**Status:** Root cause fixed in source, covered by automated tests, and verified in a freshly rebuilt native AppImage. The replacement release artifact must still be built and promoted through the updated Linux CI matrix.

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

The fresh native build also exposed an independent release-renderer failure. Pillow 13.0.0 removed `ImageMath.lambda_eval`, while the pinned `psd-tools` release still calls that API when compositing PSD previews:

```text
AttributeError: module 'PIL.ImageMath' has no attribute 'lambda_eval'
```

The runtime requirement now caps Pillow below 13, and all three hash-pinned Python lock files select Pillow 12.3.0. A clean isolated `uv` install of `requirements-lock.txt` selected Pillow 12.3.0 and exposed `ImageMath.lambda_eval`; a structural regression test keeps that compatibility ceiling in place. The corrected frozen application was then inspected directly and reported Pillow 12.3.0 from its embedded `PIL._version` module. Its packaged renderer produced a valid 220×160 JPEG from `sample.psd`, proving that the frozen PSD path no longer fails in `ImageMath.lambda_eval`.

### Release gate

`scripts/verify_linux_webkit_bundle.py` accepts a PyInstaller onedir directory or an AppImage. It requires:

- a frozen WebKitGTK 4.1 or 4.0 shared library;
- `libwebkit2gtkinjectedbundle.so` in the required `webkit_injected_bundle/` directory;
- a valid `webkit_manifest.json` with package, API, and checksum provenance; and
- matching packaged library and injected-bundle checksums with a consistent ELF dependency declaration.

The Linux build job runs this verifier both before AppImage creation and against the final downloadable `PreviewGen-Linux.AppImage`. The clean-machine Linux matrix runs the published artifact on both Ubuntu 22.04 and Ubuntu 24.04, requires the Ubuntu 24.04 host package to be genuinely newer than the recorded build-host package, and exercises Xvfb, explicit X11, and headless Wayland display sessions. A build-host/runtime WebKitGTK version split or renderer crash therefore fails before release promotion.

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
- explicit Xvfb, X11, and Wayland packaged GUI scenarios with renderer-crash checks;
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
- Corrected onedir provenance manifest: API `4.1`, package `libwebkit2gtk-4.1-0` version `2.52.6-0ubuntu0.24.04.2`, library SHA-256 `2983a129e5b223e44ce9bdf18565d51e020cafeb5f159f36fb635a43c9924618`, and injected-bundle SHA-256 `71b678905d234e44ae5a78ef0cf68128ec6ef0128b17a22e2cb1ad5e1df476af`; both packaged checksums were recomputed and matched.
- Corrected onedir dependency inspection: embedded `PIL._version` reported Pillow `12.3.0`.
- Corrected onedir packaged PSD render: `sample.psd` produced a valid 220×160 RGB JPEG with 2,252 distinct colors and 16,278 bytes.
- Corrected onedir native X11 GUI smoke test with `WEBKIT_INJECTED_BUNDLE_PATH` explicitly unset: exit `0`, `READY` marker written, and `Frontend mounted and reported ready.` in the application log.
- Corrected replacement AppImage: `appimagetool` 1.9.1 was downloaded and verified against SHA-256 `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`; the resulting AppImage had SHA-256 `d999ce503f95471a5a47f8acc56360bc824117e046dabadd41e91169da31c47a`.
- Corrected replacement AppImage verification: the release verifier found the matching injected bundle and provenance manifest under the extracted `usr/bin/_internal/webkit_injected_bundle/` directory.
- Corrected replacement AppImage packaged PSD render: `sample.psd` produced a valid 220×160 RGB JPEG with 2,252 distinct colors and 16,278 bytes.
- Corrected replacement AppImage native X11 GUI smoke test with `WEBKIT_INJECTED_BUNDLE_PATH` explicitly unset: exit `0`, `READY` marker written, and `Frontend mounted and reported ready.` in the application log.
- Journal check after the corrected native X11 onedir and AppImage runs: zero `WKBundleInitialize`, `libwebkit2gtkinjectedbundle`, or `WebKitWebProcess` crash entries.
- The corrected onedir and AppImage contained the same frontend tree as the final production build: aggregate SHA-256 `7a72322d747656c89a703a9d4045bf5bbe38042a56e60d1f5c11bab5333d2bf9`.
- The local host did not provide `xvfb-run` or Weston, so the Xvfb and Wayland scenarios remain CI acceptance gates rather than local evidence.

## Release requirements and remaining risk

A replacement AppImage was built locally from the corrected source and passed the native launch check without an environment override. This proves the implemented packaging and runtime contract on the current Linux Mint host. The local AppImage is audit evidence, not a promoted release artifact.

Before publishing a replacement release:

1. Merge this branch through the normal review process.
2. Let the Ubuntu 22.04 build job create the AppImage with the corrected hook.
3. Require the bundled-artifact verifier to pass against both the onedir and final AppImage.
4. Require the Ubuntu 22.04 and Ubuntu 24.04 clean-machine jobs to prove newer-host ordering where applicable and to pass the Xvfb, X11, and Wayland packaged GUI scenarios.
5. Promote the resulting artifact only after those native checks pass.

The Ubuntu 24.04 clean-machine job has not run in this local session because the branch has not been pushed. It remains the required proof that the release catches distribution drift. Passing Ubuntu 22.04 and 24.04 does not certify every Linux distribution; the README now states that limitation explicitly.
