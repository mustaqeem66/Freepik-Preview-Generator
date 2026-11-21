# PreviewGen Remediation TODO

This checklist compares the public GitHub branch with the user-supplied `PreviewGen_AUDIT_REPORT_v2.md`. That report was produced from a different snapshot. Treat its pass counts as **unverified against current main** until the exact source archive has been reconciled.

## Round-2 findings (NEW-1..NEW-8)

- [x] NEW-1: the frontend binds to the returned operation id, buffers startup events, and rejects a superseded terminal event.
- [x] NEW-2: supersede joins run on the new worker thread; the JS bridge call returns immediately.
- [x] NEW-3: completion callbacks carry the run's own operation id instead of reading shared mutable state.
- [x] NEW-4: `skip` tolerates an unreadable pre-existing JPG and still reports `skipped: true`.
- [x] NEW-5: AppleScript literal encoding moved to GUI-independent `previewgen.dialogs` and used by the fatal-error dialog.
- [x] NEW-6: obsolete — PowerShell now opens Inno Setup, which owns uninstall registration and removal.
- [x] NEW-7: discovery emits `planned: -1`; the frontend clamps it to an indeterminate bar.
- [x] NEW-8: dead legacy batch callback globals removed from the bridge and type declarations.
- [x] README truth pass: removed unmeasured throughput, 60 FPS, Framer Motion, deep-ZIP, ICC and palette claims.

## Release blockers

- [x] Repair normal desktop startup: gate the smoke auto-close watchdog.
- [x] Track batches via lifecycle; cancel only active batch work, not scans.
- [x] Prevent old batch progress/completion from replacing the next batch UI state; return operation IDs.
- [x] Avoid joining a cancelled batch in a UI bridge call.
- [x] Bound event summary payloads; keep full file records in on-disk report.
- [x] Honor single-export overwrite/rename/skip behavior, including corrupt existing skipped outputs.
- [x] Stop preview HTTP server during desktop cleanup.
- [x] Add regression tests and a pull-request CI gate.
- [x] Align planned v2.1.2 version in Python, frontend and installer sources.
- [x] Pass full PR CI (Ruff, pytest, TS, Vitest, build); packaged Windows GUI smoke passes on a clean CI runner (build run 39921711896).
- [ ] Reconcile missing audited v2.1.1 source code and tests before publishing v2.1.2.
- [x] Reproduce and repair missing Collada renderer dependency across source, hash locks, frozen binary and release fixtures.
- [x] Verify DXF at 512/1024/2400 after matplotlib finalize (aspect preservation remains covered by the renderer and manual checks).
- [ ] Exercise actual Windows installer/uninstaller/desktop icon/custom directory and non-smoke startup on a clean Windows VM.
- [x] Verify macOS shell checksum fallback with `shasum`/`openssl` and no `sha256sum` on `PATH`.
- [x] Align every advertised format with release-gate fixture or an explicit limitation (registry already carries a caveat for every extension; the renderer audit added 3MF/IGES/PBR fixtures).

## Desktop experience

All eight items below were implemented after this checklist was written. Each was
re-verified against `main` on 2026-11-19; the original text is kept so the
change of state stays auditable.

- [x] Add an **Add Files** native multi-select path in parallel with the folder-only chooser; never change the folder dialog into a file dialog. — `DesktopApi.browse_files` uses `allow_multiple=True` and grants **exact file paths only**; no directory is added, so picking a file never grants its siblings or parent. The folder dialog is untouched. 5000-file cap on both the selection and the grant set.
- [~] Implement and test file-based ingestion for batch export, preview, drag/drop and reporting; don't offer selection that can't be exported. — **Batch export, preview and reporting** are done: `DesktopApi.start_batch_files` and `process_folder(selected_files=…)` carry picked files through preview, batch and reporting, with `sourceIndex` disambiguating same-name picks. **Drag/drop is not implemented** — see the item below.
- [~] Add accessible drag/drop empty state, unsupported file explanation, searchable asset list. — **Searchable asset list** and **unsupported file explanation** are done: `FileList` filters by filename while keeping the original source indices so a filtered result cannot retarget a different file, and `App.tsx` renders the probe's `previewSupport.caveat` in a `role="note"` block. **Drag/drop is not implemented** — no drop handler exists anywhere in `frontend/src`. The empty state is keyboard-reachable, so the remaining gap is the drop target itself.
- [x] Create design tokens, improve small typography/spacing, keyboard focus and contrast. — 60 custom properties in `frontend/src/index.css` with light/dark palettes; 3px `:focus-visible` rings; functional labels at 12px with 10–11px reserved for short badges. **Contrast was re-audited on 2026-11-19** and now has a regression gate in `tests/frontend/test_theme_contrast.py`.
- [x] Create resizable library/preview/inspector panes and collapsible controls. — `PaneResizer` with keyboard support.
- [x] Add before/after preview, checkerboard and zoom-to-fit. — `BeforeAfterComparison` plus the canvas zoom/pan and fit controls.
- [x] Add native desktop toast notifications for completion/failure with opt-in preferences; no intrusive always-on-top popup. — `previewgen/notifications.py`, persisted as an opt-in setting that defaults to **off**; failures are non-fatal and never block the bridge.
- [x] Add presets, batch queue and cancel state UX. — `StylePresetManager` (grant-safe: a preset never changes `logoPath`, `fontPath`, `inputFolder` or `outputFolder`) and `BatchProgress` with cancel state.

## Security, operations and performance

- [x] Restrict bridge path authorization to user-selected or committed roots (no implicit expansion during export).
- [x] Add and regression-test a restrictive CSP compatible with packaged frontend and pywebview (`frontend/security/csp.ts`, WebKit enforcement in `scripts/verify_csp_webview.py`, now a Linux packaging gate against the frozen HTML).
- [x] Review untrusted ZIP, Blender, DXF, CAD, font, SVG and model parsing and subprocess time budgets.
- [ ] Replace per-file process spawn only after a measured, isolated worker-pool design passes cancellation and crash tests.
- [x] Benchmark advertised throughput; fix README claims (README truth pass removed the 60fps, deep-ZIP, Framer Motion, ICC and 500-files/60s claims).
- [ ] Create signed versioned builds, updater, rollback and reproducible release provenance.
- [x] Pin release actions by commit SHA and remove hardcoded signtool locations (every `uses:` is SHA-pinned; signtool is discovered from the installed Windows SDK).
- [ ] Add crash logs/diagnostics with consent and no automatic collection of artwork.

## Round-3 audit remediation (branch `fix/v2.1.2-audit-hardening`)

Each row names the gate that proves it. Python rows run under the PR CI
`pytest tests/ -q` gate; frontend rows run under `npx vitest run`; workflow rows
are gated by the `build` job on tag pushes.

| Finding | Fix | Gate |
| --- | --- | --- |
| Watchdog declared the bridge stalled on an idle app | `bridge_is_stalled()` requires a quiet heartbeat **and** outstanding work | `tests/unit/test_watchdog_stall_detection.py` |
| Single export of a ZIP member defaulted to the deleted temp dir, and hid work from the watchdog | default destination is the archive's folder; export registers an `ActiveOperation` | `tests/unit/test_batch_api_regressions.py` |
| Terminal bridge events arriving before the start promise resolved were dropped | buffer-and-replay gated on the returned operation id | `usePreview.test.ts`, `useAssetProbe.test.ts` |
| Stale export-size responses overwrote newer input; picking another asset kept a live request | local commit plus per-file request-sequence invalidation | `ExportSizePanel.test.tsx` |
| Cached `window.pywebview.api` survived reload; selection index derived from a stale file list | cache follows the live bridge object; selection is real state | `bridge.test.ts` |
| Blender invoked with `-Y`; dense meshes were stride-subsampled, leaving holes | `--disable-autoexec`; every visible face drawn, with vectorized 2x2 splats for subpixel triangles | `tests/unit/test_mesh3d_hardening.py` |
| Nested ZIPs extracted one level deep, failures suppressed, no shared budget or cancellation | depth-capped BFS extraction on one shared byte budget, failures reported, cancel-aware | `tests/unit/test_archive_security.py` |
| Embedded BMP search matched any `BM` pair; EXIF orientation dropped on embedded thumbnails | header-validated BMP discovery; `exif_transpose` inside `bounded_image_from_bytes` | renderer/unit suites |
| `text_pos` magic-number override silently beat the chosen anchor | custom position is opt-in only | compose unit tests |
| `install.sh` warned then continued with no `SHA256SUMS.txt`, and stripped quarantine silently | fail-closed `verify_checksum`; Gatekeeper choice left to the user | `tests/unit/test_installers.py` |
| CI published unsigned / un-notarized release artifacts when signing secrets were absent | `PREVIEWGEN_IS_RELEASE` guards fail tag builds; macOS signature is verified | `.github/workflows/build.yml` |
| `softprops/action-gh-release@v2` was a mutable ref | pinned to `3bb12739c298aeb8a4eeaf626c5b8d85266b0e65` (v2.6.2) | PR CI |
| `*.spec` was ignored under an "internal docs" rationale while PyInstaller emits one | rule moved under build artifacts with the reason recorded | `.gitignore` |

**Release policy:** No merged PR should be described as production-ready solely because unit tests pass. Require Windows startup, file-dialog, installer, export, and renderer smoke tests on a clean machine.

## 2026-10-21 — Settings persistence recovery (proposed PR)

- [x] Save attempts now have visible `loading/unsaved/saving/saved/error` states; a skipped or failed bridge call is never presented as saved.
- [x] Transient persistence failures retry with bounded backoff (0.5, 1, 2 seconds), with a manual retry action.
- [x] Stale saves are guarded by a per-snapshot monotonic revision and effect cancellation; reconnection restarts the save effect.
- [x] Add frontend regression coverage for failed saves, transient recovery and revision monotonicity.
- [ ] Verify with `cd frontend && npm ci && npm run typecheck && npm test && npm run build` (not executed in this GitHub-connected session).
- [ ] Validate manual disconnect/reconnect and OS shutdown persistence with a real desktop build. A sudden process kill may still lose in-memory changes.

## 2026-10-23 — Renderer format audit (branch `fix/renderer-format-audit`)

| Finding | Fix | Gate |
| --- | --- | --- |
| `.3mf` advertised but `trimesh`'s 3MF loader imports `lxml`/`networkx`, which were absent from every lock | direct pins, lock regeneration, `--collect-all` in the release build, fixture manifest entry | `tests/integration/test_release_renderers_gate.py`, `tests/fixtures/renderer-samples.json` |
| `.igs`/`.iges` parsed with the STEP reader and always failed | reader selected from the extension before `cascadio.to_glb_bytes` | `tests/unit/test_cad_hardening.py` |
| Untextured PBR GLB raised `IndexError` through lazy `face_colors` | visuals normalized to per-face/per-vertex arrays with a guarded fallback | `test_mesh3d_hardening.py::test_untextured_pbr_glb_renders` |
| Dense meshes were stride-subsampled, leaving transparent holes | all visible faces drawn; subpixel triangles splatted in one vectorized pass | `test_mesh3d_hardening.py::test_dense_mesh_draws_every_face_without_holes` |
| Z-up sources (STL/3MF/CAD kernels) rendered lying on their side | explicit Z-up to Y-up transform for those formats | `test_mesh3d_hardening.py::test_z_up_models_are_rotated_upright` |
| DWG previews with exactly one bitmap record were rejected | record count check accepts one, rejects zero | `tests/unit/test_cad_hardening.py` |
| Non-finite vertices, empty geometry and blank renders surfaced as opaque failures | explicit `ValueError`s and a blank-output guard | `test_mesh3d_hardening.py` |

## 2026-10-23 — Full-repository defect audit (branch `fix/audit-2026-10-23`)

Audit performed directly on `main` at `101b9af`; each fix ships with a regression test.

| Finding | Fix | Gate |
| --- | --- | --- |
| Every PSD preview leaked the open foreground document (layer data, file handle, mmap) in the long-lived gallery worker | `_load_psd` closes the `PSDImage` in a `finally`, including when `composite()` fails | `tests/integration/test_psd_renderer.py` |
| A failed atomic settings write left its partially written `settings_*.tmp` in the settings directory | each failed attempt removes its temp file before retrying | `tests/unit/test_settings_ordering.py` |
| A temp directory whose owner marker could not be read was pinned forever, permanently leaking extraction output after a crash mid-marker-write | an unreadable marker is treated like a missing one: reclaimed only past `STALE_AGE_SECONDS` (fresh directories still protected by `MINIMUM_DELETION_AGE_SECONDS`) | `tests/unit/test_startup_cleanup.py`, `tests/unit/test_backend_audit_regressions.py` |
| Preview frames sorted lexicographically; past six digits the newest frame sorted below older ones and was pruned while still referenced | frame pruning orders by the numeric publish counter | `tests/unit/test_preview_server.py` |
| GUI/main-process ZIP paths materialized the entire central directory before the member cap was applied (memory exhaustion via a small archive declaring millions of entries) | count the **actual** central-directory records from the same bytes `ZipFile` reads (the EOCD total can understate them) and refuse oversized archives before constructing `ZipFile`; all extraction sites use `open_zip_bounded` | `tests/unit/test_resource_limits.py` |

The corrupt-owner-marker change supersedes the narrower rule added in #78: both an unmarked and an unreadable-marker directory are equally unprovable, and the stale-age bound is the actual safety mechanism. Leaving corrupt markers alone made the leak permanent.

## 2026-10-24 — Second full-repository audit (branch `fix/audit-2026-10-24`)

Audit performed directly on `main` at `576b6a2`; each fix ships with a regression test. Modules reviewed in full: `api`, `assets`, `batch/*`, `cli`, `config`, `destinations`, `entrypoint`, `lifecycle`, `limits`, `preview_coordinator`, `probe_coordinator`, `probe_process`, `proc`, `processor`, `renderer_process`, `renderers/*`, `resources`, `scanner`, `settings`, `thumbnail_coordinator`, `worker_slot`, and the main frontend bridge/hooks/components.

| Finding | Fix | Gate |
| --- | --- | --- |
| A failed `WorkerSlot` spawn leaked both multiprocessing queue pipes (and their feeder threads) plus the Windows Job Object handle for the slot's lifetime | close the queues/job and reap a partially started child before re-raising | `tests/unit/test_preview_coordinator.py::test_worker_slot_closes_queues_when_process_start_fails` |
| `probe_asset_isolated` created its result queue outside the `try`, so a failed `process.start()` leaked the queue | start the process inside the guarded block so the existing `finally` disposes the queue | `tests/unit/test_probe_process.py::test_probe_asset_isolated_closes_queue_when_start_fails` |
| Procreate (`procreate`/`brush`/`brushset`), Krita and Fusion 360 thumbnail paths opened `zipfile.ZipFile` directly, materializing an unbounded central directory | route every archive through `limits.open_zip_bounded`; Fusion thumbnails also bound the actual member stream, not just the declared size | `tests/unit/test_renderer_audit_regressions.py::test_creator_archives_open_through_the_bounded_zip_reader`, `::test_f3d_thumbnail_opens_through_the_bounded_zip_reader` |
| Illustrator/EPS embedded-thumbnail fallbacks decoded unbounded bytes with `Image.open`, and the Pillow EPS fallback rendered at the file's declared bounding box without a size cap | all embedded previews use `limits.bounded_image_from_bytes`; the EPS render checks `limits.check_raster_size` before `load()` | `tests/unit/test_creator_formats.py`, `tests/unit/test_renderer_audit_regressions.py` |

Not changed after review: `LifecycleManager.start_batch` joins the superseded worker thread from the new worker thread only (never the bridge thread), which is required to keep output writes serialized; and `ActiveOperation.process_ids` is defense-in-depth metadata for shutdown logging, while actual renderer children are owned and reaped by their coordinators. Neither is a functional defect.


## 2026-11-19 — Deep audit of `main` at `6a18d9e`

Audit performed directly on `main` after the CI flake fixes in #159 and #160.

> **Correction (2026-11-20).** The 2026-11-19 round fixed colour tokens in
> `frontend/src/index.css` and shipped a stylesheet-level test. Measuring the
> **computed** colours of the built bundle in a real browser showed that two
> of those fixes never reached the UI: the palette was declared in three
> `:root` blocks across `index.css` and `studioPremium.css`, and
> `studioPremium.css` is imported last, so its values silently won. The
> `--text-muted` fix in particular was dead code — the shipped value was still
> `#69768a`, and the studio badge, the format notes and the slider hints were
> rendering between 3.92:1 and 4.41:1.
>
> The 2026-11-20 round below fixes the defect at its root and replaces the
> blind spot with a gate that measures the shipped artifact. The 2026-11-19
> entries are kept for the record.

| Finding | Fix | Gate |
| --- | --- | --- |
| The primary button's gradient put its white 12px label at **2.90:1** (light) and **3.25:1** (dark) against the gradient's light end — under the WCAG AA 4.5:1 floor for normal text | the gradient stops were darkened to `#2676cc` / `#1a6fc8`; the worst point on each gradient is now 4.62:1 and 5.03:1 | `tests/frontend/test_theme_contrast.py::test_white_button_label_is_readable_across_the_whole_gradient` |
| Accent-coloured text used the solid `--accent` fill token, which reaches only **2.60:1** on the dark surface | a dedicated `--accent-text` token was added (`#0067d4` light, `#4da3ff` dark) and every accent-as-text rule now uses it | `tests/frontend/test_theme_contrast.py::test_accent_text_is_readable_on_every_surface` |
| The dark `--text-muted` token sat at **4.22:1** on the page background | darkened to `#6b6b75` (4.67:1 on `--bg`, 5.05:1 on `--card`) — **superseded by the 2026-11-20 round, which fixed the token that actually ships** | `tests/frontend/test_theme_contrast.py::test_secondary_text_is_readable_on_every_surface` |
| The pressed focus button painted accent text over the tinted `--selection` surface, which lands at **4.16:1** in dark mode | that one state uses `--text` instead (9.69:1) | `tests/frontend/test_theme_contrast.py::test_accent_text_is_readable_on_the_selection_surface` |
| The Vitest worker-pool bound still used the `poolOptions` shape that **Vitest 4 removed**, printing a deprecation warning on every run | migrated to the current top-level `maxWorkers` / `minWorkers` options; the bound now applies without the warning | `frontend/vite.config.ts`, verified by a clean `npm test` run |

### Verified unchanged in this audit

The Windows hang fix (#74) is intact: the `DesktopApi` bridge surface is still flat
(41 public names, no `_window`), every coordinator object still carries
`_serializable = False`, and `tests/unit/test_bridge_surface_exposure.py` passes.
The batch cancel-race fix (#159) holds under a deterministic regression test, and
the native-picker child now exits with a diagnostic instead of hanging until the
parent's timeout (#160).

## 2026-11-20 — The palette had no single authority

Found by measuring the **computed** colours of the built bundle in a real
browser rather than reading the CSS source. Every ratio below was measured in
the rendered document.

| Finding | Fix | Gate |
| --- | --- | --- |
| The palette was declared in **three `:root` blocks across `index.css` and `studioPremium.css`**, plus two competing `prefers-contrast: more` blocks. Because `studioPremium.css` is imported last, its values silently won: a token "fixed" in `index.css` never reached the browser. This is what made the 2026-11-19 contrast fixes ineffective | `index.css` is now the single authority for the palette; the duplicate blocks were removed and `studioPremium.css` contributes only `--canvas-dot` and `--studio-shadow`. The built bundle now declares each palette token exactly once per theme | `tests/frontend/test_theme_contrast.py::test_the_palette_has_a_single_authority` |
| The effective `--text-muted` was `#69768a`, which reaches **3.92:1** on `--chip-bg` and **4.07:1** on `--bg`. The studio badge, the format notes and the slider hints were all below the WCAG AA 4.5:1 floor | changed to `#5f6977`, which clears **4.74:1** on the worst surface in the theme | `tests/frontend/test_theme_contrast.py::test_secondary_text_is_readable_on_every_surface`, `scripts/verify_theme_contrast.py` |
| The dark primary button's white label sat on the bright `#5298fb` accent at **2.90:1** | a new `--accent-label` token carries `#15191f` in dark mode (**6.08:1**) and `#ffffff` in light mode (**5.63:1**) | `tests/frontend/test_theme_contrast.py::test_accent_filled_button_label_is_readable`, `scripts/verify_theme_contrast.py` |
| The stylesheet-level test read one file, so it could not see an override in another file | the test now resolves the **effective** palette in import order, exactly as the cascade does, and asserts that no other file may redefine a palette token | `tests/frontend/test_theme_contrast.py` |
| Nothing measured the shipped artifact, so a colour could pass every source-level check and still fail on screen | `scripts/verify_theme_contrast.py` loads the built bundle in **WebKitGTK** — the engine behind the Linux pywebview window — measures every rendered text node in both themes and fails below the WCAG AA floor. It drives the real theme toggle, so React's own state is exercised | `scripts/verify_theme_contrast.py`, wired into `build.yml` on Linux |

The consolidation was verified to be behaviour-preserving: every computed token
is identical to the pre-consolidation build except the newly added
`--accent-label`, and every rendered text node keeps the same foreground and
background pair.

Two failure modes the gate is explicitly required to catch, because either one
would let a broken measurement report success:

| Failure mode | How the gate refuses it |
| --- | --- |
| The theme toggle does not take effect, so the dark theme is never measured and both passes report the light theme's colours | the gate compares the two themes' resolved foreground colours and fails when they are identical |
| The build step packages a different stylesheet than the one that was measured | the gate runs against `frontend/dist` **and** against the `index.html` that PyInstaller froze into the artifact, matching the CSP gate's convention |

The first failure mode was confirmed by stubbing the theme toggle out: the
gate reports "both themes resolved to the same foreground colours" and exits
non-zero instead of passing.

## 2026-11-20 — The Windows clean-machine gate blamed the frontend for a browser-process abort

Found while running the build workflow, not by reading the code. The
`Clean Machine Test (windows-latest)` job failed reproducibly (2 attempts) with:

```
[ERROR] pywebview: WebView2 initialization failed with exception:
  (0x80004004): Operation aborted (Exception from HRESULT: 0x80004004 (E_ABORT))
   at Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateCoreWebView2ControllerAsync
```

The app then logs an orderly shutdown and exits with code 0, so the test
reported "frontend_ready marker not written; the packaged WebView never became
ready" — a message that points at the frontend when the WebView never started
at all. The abort happens while the **browser process is being created**, so
the frontend HTML is never parsed and nothing in the bundle can be
responsible.

This reproduces on unmodified `main` (`a0d9f1c`) with the identical error, on
the same runner image (`windows-2025-vs2026`, runner `2.338.2`) that the
passing runs used. It is therefore an environment condition, not a defect
introduced by any change. The underlying cause of the abort inside the
WebView2 runtime on a busy CI runner is **not yet established**; the
observation is filed on issue #19.

The gate now retries the launch up to three times, but **only** when the log
shows the browser-process abort. Any other reason for the missing marker still
fails immediately, and the issue #19 bridge-injection check still runs after
the retry loop, so a real regression cannot be masked by a retry. The aborted
attempt's log is preserved so the failure stays diagnosable even when a later
attempt succeeds.

### Not verified in this audit

Native installer operation, Windows/macOS idle behaviour, renderer image fidelity
against an independent oracle, and code signing/notarization remain unproven —
they need real machines and signed artifacts, and are tracked in
`docs/engineering/2026-10-28-audit-verification-progress-and-release-plan.md`.

## November audit continuation — packaged WebView and release evidence

- **Windows idle (#19):** The freeze reproduced, and its cause is confirmed.
  The *installed* 2.1.2 build gave 1 responsive and 100 unresponsive samples
  over 300 seconds, and its log shows the pywebview bridge walking
  `window.native...` — the injection storm that PR #74 fixed. That installed
  build predates the fix commit `de1b6e6`. The CI candidate that **contains**
  the fix gave 99 responsive, 0 unresponsive and a monitor exit code of 0,
  with no bridge injection errors in its own log. The bridge fix therefore
  removes the freeze on Windows at 100% DPI. The portable build's earlier
  probe failed differently: 83 responsive samples, then 18 with no window, and
  an orderly shutdown with no established cause. See
  `docs/WINDOWS_HANG_INVESTIGATION.md` for exact artifacts, runtime and
  evidence. Still open: the installed build, the installer/upgrade/uninstall
  path, and the 125/150/200% DPI matrix.
- **CSP (#20):** Clean-machine CI now checks the live bridge and a decoded
  loopback JPEG, together with denial of inline and blob scripts. Socket
  errors and elapsed time are not accepted as proof of a CSP block. A Linux
  WebKitGTK run of the desktop runtime blocked both scripts with the
  production bundle; removing the CSP from a throwaway copy executed both
  scripts and failed the checker while the JPEG still decoded. The broader
  WebKitGTK harness matched all 11 expected outcomes, with three engine
  refusals captured. The fresh local PyInstaller build timed out; exact
  packaged verdicts for this change remain unverified. CSP is not a sandbox.
- **Release (#22):** Tagged CI stages a draft instead of publishing a stable
  release after smoke tests alone. The checksum step rejects missing
  binaries. Review exact-artifact receipts before publishing. The
  Windows CI candidate's portable EXE and setup both reported `NotSigned`
  through Windows Authenticode; they are not signing evidence.
  The signing gate now *reads the signature back* instead of trusting
  `signtool sign` to exit zero: the Windows job verifies the Authenticode
  status of both `PreviewGen.exe` and `PreviewGen-Setup.exe`, requires a
  signer certificate, and requires an RFC3161 timestamp, so an unsigned or
  untimestamped artifact fails the build. The release job now produces a
  detached GPG signature over `SHA256SUMS.txt`, verifies that signature
  before publishing it, and publishes the public key beside it. `install.ps1`
  now verifies that detached signature against the published key and reads
  back the installer's Authenticode signature, instead of trusting a
  checksum fetched from the same release it is supposed to protect. These
  are enforced by `tests/unit/test_ci_workflow_config.py`.
  Still open: the signing material (`WINDOWS_CERTIFICATE`, `MACOS_CERTIFICATE`,
  `GPG_PRIVATE_KEY`, `GPG_KEY_ID`) is not configured in this repository, so
  no signed release can be produced until those secrets are supplied, and the
  Windows candidate still reports `NotSigned`.
- **Renderers (#60):** The strict gate is implemented and fails correctly.
  `scripts/audit_renderer_matrix.py --verify-fixtures --strict` was run
  against the current tree and reported: 11 of 46 previewable extensions have
  a fixture, all 12 fixtures render without failure, and **0 of 12** have an
  independently approved visual oracle. The 35 extensions without a fixture
  are `.abr`, `.afdesign`, `.afphoto`, `.afpub`, `.ai`, `.blend`, `.bmp`,
  `.brush`, `.brushset`, `.clip`, `.dwg`, `.eps`, `.f3d`, `.gif`, `.gltf`,
  `.ico`, `.iges`, `.indd`, `.jpeg`, `.kra`, `.ma`, `.max`, `.mb`, `.otf`,
  `.ply`, `.procreate`, `.stl`, `.stp`, `.svgz`, `.tif`, `.tiff`, `.ttf`,
  `.webp`, `.woff`, `.woff2`.
  The gate already refuses synthetic oracles, requires an identified
  independent source application with a version, and requires a named human
  reviewer, so the remaining work cannot be completed by generating more
  fixtures: it needs licensed, versioned authoring-application samples and a
  recorded human review of each reference image. The capability catalog is
  consistent (`advertisedWithoutCapability` and
  `catalogWithoutAdvertisedExtension` are both empty) and every format
  declares its own fidelity caveat, so the app does not overpromise.
  Report: `renderer-matrix-local.json`.
- **Studio 2.2 (#23):** The engineering and UX work in this tracker is
  complete; the release work is not. Resizable panels, the command palette,
  the bounded thumbnail browser and the native Add Files path are all
  implemented. An axe-core 4.13.0 audit of the production bundle in a real
  browser engine found and fixed three accessibility defects: invalid
  grid-only ARIA (`aria-rowcount`/`aria-rowindex`) on the asset listbox,
  a format badge dimmed with `opacity: 0.6` that measured 3.91–4.21:1
  against the surface, and two independently scrolling panes that were not
  keyboard reachable. The audit now reports **0 violations** in both light
  and dark themes. See `docs/PREMIUM_UI_UX_PLAN.md`.
  The frontend test run also reported `Errors 1` while every test passed.
  Vitest exits non-zero on an unhandled error, so this would have failed the
  CI gate despite a green test list. The cause was real: `useBackend` awaited
  `ApiBridge.getApi(4000)` outside its error boundary, and reading
  `window.pywebview.api` can throw while pywebview tears the bridge down
  mid-navigation. The wait is now guarded, and `ApiBridge` reads the live
  bridge through a helper that cannot let a teardown throw. A regression test
  drives a throwing `window.pywebview` getter and asserts the handshake
  resolves rather than rejects.
  Keep open: source tests and native smoke are distinct from installed
  workflows, cross-platform grants and picker acceptance, release signing
  and independent visual fidelity. The Windows and macOS DPI matrix,
  real screen-reader behaviour, and a signed release remain unverified.
