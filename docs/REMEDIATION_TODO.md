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
- [ ] Pass full PR CI (Ruff, pytest, TS, Vitest, build), verify on Windows GUI.
- [ ] Reconcile missing audited v2.1.1 source code and tests before publishing v2.1.2.
- [x] Reproduce and repair missing Collada renderer dependency across source, hash locks, frozen binary and release fixtures.
- [x] Verify DXF at 512/1024/2400 after matplotlib finalize (aspect preservation remains covered by the renderer and manual checks).
- [ ] Exercise actual Windows installer/uninstaller/desktop icon/custom directory and non-smoke startup on a clean Windows VM.
- [x] Verify macOS shell checksum fallback with `shasum`/`openssl` and no `sha256sum` on `PATH`.
- [ ] Align every advertised format with release-gate fixture or an explicit limitation.

## Desktop experience

- [ ] Add an **Add Files** native multi-select path in parallel with the folder-only chooser; never change the folder dialog into a file dialog.
- [ ] Implement and test file-based ingestion for batch export, preview, drag/drop and reporting; don't offer selection that can't be exported.
- [ ] Add accessible drag/drop empty state, unsupported file explanation, searchable asset list.
- [ ] Create design tokens, improve small typography/spacing, keyboard focus and contrast.
- [ ] Create resizable library/preview/inspector panes and collapsible controls.
- [ ] Add before/after preview, checkerboard and zoom-to-fit.
- [ ] Add native desktop toast notifications for completion/failure with opt-in preferences; no intrusive always-on-top popup.
- [ ] Add presets, batch queue and cancel state UX.

## Security, operations and performance

- [x] Restrict bridge path authorization to user-selected or committed roots (no implicit expansion during export).
- [ ] Add and regression-test a restrictive CSP compatible with packaged frontend and pywebview.
- [x] Review untrusted ZIP, Blender, DXF, CAD, font, SVG and model parsing and subprocess time budgets.
- [ ] Replace per-file process spawn only after a measured, isolated worker-pool design passes cancellation and crash tests.
- [ ] Benchmark advertised throughput; fix README claims (60fps orbit, deep ZIP recursion, Framer Motion, ICC transform, 500 files/60s).
- [ ] Create signed versioned builds, updater, rollback and reproducible release provenance.
- [ ] Pin release actions by commit SHA and remove hardcoded signtool locations.
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
| Blender invoked with `-Y`; full-scene face path unbounded | `--disable-autoexec`, resolution-scaled face budget | `tests/unit/test_mesh3d_hardening.py` |
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
