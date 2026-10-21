# Explicit-file picker and batch support — 2026-10-21

## Root cause
The existing folder-based batch runner uses `discover_files(input_folder)` and `relative_to(input_folder)`. Returning arbitrary selected files from unrelated directories to the frontend would therefore not generate them in a batch. Granting parent directories would broaden write authorization unnecessarily.

## Implementation
- `DesktopApi.browse_files()` opens the native OPEN_DIALOG with multi-select and returns each selected supported image's name, canonical path, extension and 3D flag, alongside actionable rejection messages.
- A session-lifetime `_authorized_files` set keeps exact read grants distinct from existing `_authorized_folders` write permissions. Selecting `C:/art/a.png` does **not** authorize `C:/art/`.
- `DesktopApi.start_batch_files()` validates that every supplied file has a picker grant, exists, matches the allowed extensions and meets the 5000-file UI cap. It requires a separately authorized output folder.
- `LifecycleManager.start_batch(selected_files=...)` routes the same bounded, cancellable operation through the existing `process_folder` renderer/reporting pipeline, avoiding directory traversal. Archive extraction, output rename/skip policy, isolation/timeouts, progress events and durable reports are reused.
- The existing `start_batch(input_folder,...)` and command-line folder batch path remain unchanged.
- Security/unit tests cover individual file grant scope, injected input paths, unauthorized output and multi-folder JPG generation.

## Known limits and review requirements
- `browse_files` returns a maximum of 5000 files per call (larger selections require another set). UI must display unsupported/missing files.
- Existing preview/probe endpoints accept arbitrary file paths in the already-authorized frontend session; this PR does not claim the general bridge is sandboxed. Exact selection checks apply to `start_batch_files`.
- This backend PR does not add the frontend button yet. Merge/test backend before stacked frontend PR.
- Some native WebView file pickers differ in their tuple/list return shapes; verify Windows WebView2, macOS Cocoa and Linux GTK/Qt.
- Symlink targets are canonicalized and rechecked at batch start; do not interpret this as an OS-level ACL.
- [ ] Run `python -m ruff check previewgen/api.py previewgen/lifecycle.py previewgen/batch/runner.py tests/unit/test_native_add_files.py`.
- [ ] Run `python -m pytest tests/unit/test_native_add_files.py tests/unit/test_batch_api_regressions.py tests/unit/test_discovery.py -q`.
- [ ] Real desktop export/cancel and ZIP coverage before merging; no GitHub Actions minutes are used.

## Review corrections
- The source-folder chooser is **not** an output authorization for selected-file batches. `add_authorized_output_folder()`, invoked by the output picker or restored output preference, provides a distinct destination grant.
- Across repeated selections, a maximum of 5000 exact file grants are retained for this desktop session. No parent directory is authorized by Add Files.
- A raw `.zip` is not a previewable row; the picker rejects it with instructions to select its containing folder, whose scan exposes `zip://` member assets. Folder ZIP processing remains supported.
- For selected regular files, JSON file records include a per-run `sourceIndex` plus the filename, distinguishing identically named inputs **without exposing absolute source directories**. CSV continues to store filenames for compatibility.
- Expanded regression checks cover duplicate basenames, rejected ZIP files, source-vs-destination permissions and separate folders.

## 2026-10-21 security and lifecycle review
- `DesktopApi.save_settings` now rejects an unapproved nonempty `outputFolder`. Otherwise a bridge caller could persist an unselected destination and invoke `get_initial_state` to turn that preference into an output grant. Preferences previously saved through the native chooser can still be restored on restart.
- `DesktopApi.export_preview` requires an **explicit output chooser grant** when the source is an individual picker-selected file; a source-folder scan cannot silently act as the destination grant.
- `DesktopApi.clear_selected_files` revokes session-scoped exact-file read grants when the user clears their selection. A running batch uses the already-validated snapshot and must be cancelled separately.
- A selected-file report records `sourceIndex` only; do not serialize absolute input paths into reports intended for sharing. Report consumers should tolerate this optional extra JSON field.
- New tests cover settings-grant escalation, selected JPG destination enforcement, grant revocation, replay rejection, and path redaction.
- Local native verification remains mandatory. `[skip ci]` is a billing constraint, **not** a passing test.
