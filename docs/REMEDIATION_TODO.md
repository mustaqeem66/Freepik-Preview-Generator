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
- [ ] Review untrusted ZIP, Blender, DXF, CAD, font, SVG and model parsing and subprocess time budgets.
- [ ] Replace per-file process spawn only after a measured, isolated worker-pool design passes cancellation and crash tests.
- [ ] Benchmark advertised throughput; fix README claims (60fps orbit, deep ZIP recursion, Framer Motion, ICC transform, 500 files/60s).
- [ ] Create signed versioned builds, updater, rollback and reproducible release provenance.
- [ ] Pin release actions by commit SHA and remove hardcoded signtool locations.
- [ ] Add crash logs/diagnostics with consent and no automatic collection of artwork.

**Release policy:** No merged PR should be described as production-ready solely because unit tests pass. Require Windows startup, file-dialog, installer, export, and renderer smoke tests on a clean machine.
