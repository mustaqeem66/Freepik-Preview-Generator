# PreviewGen Add Files: UI integration — 2026-10-21

## End-to-end source mode
- Add Files opens the OS multi-select dialog. Multiple picker rounds accumulate canonical file paths without duplicates. Unsupported/missing files are displayed as warnings.
- A separate Files mode displays the selected assets while preserving the folder scanner's collection. Folder switches back; Clear files discards the session selection.
- Selecting files turns off "Same as input"; a separate authorized output directory is required before exporting.
- Existing image preview, 3D orbit, probing, sizing, single-JPG export, cancellation and reports work against the selected asset list.
- Selected-file batch passes only exact file paths to `start_batch_files` in backend PR #34; folder batches continue using `start_batch`.
- The command palette exposes Add Files and inherits the same readiness/permission guards.
- No OS file paths are accepted directly from a browser drag/drop event and no source parent gains write authorization.

## Dependency and outstanding tests
This is stacked on PR #34. Merge and verify backend first, then retarget this PR to main and run the combined local suite.
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] `python -m pytest tests/unit/test_native_add_files.py tests/unit/test_batch_api_regressions.py -q`
- [ ] Native Windows, macOS and Linux dialogs; select multiple assets from unrelated folders, preview/individual export/batch/export report/cancel.
- [ ] Missing files, duplicate basenames, ZIP, incompatible formats, inaccessible destination, and app restart.
- [ ] Keyboard and screen readers, 1100x700 layout, high DPI, Focus Canvas, command palette.
The code is untested in this environment; drafts and [skip ci] preserve the hosted Actions budget.
