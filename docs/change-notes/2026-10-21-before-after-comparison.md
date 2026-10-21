# Before / After source comparison — 2026-10-21

## Purpose and accuracy
Add an **opt-in**, workspace-native comparison between the source artwork visualization and the current branded PreviewGen JPG preview. This is not a comparison with an exported file read back from disk, nor a byte-accurate view of native editable formats.

- **Before (Source):** The supported source is decoded into a bounded RGBA image in the isolated renderer and displayed over a neutral checkerboard. No diagonal composition, watermark text, logo or inspector overlays are applied. Raster artwork retains its appearance apart from necessary resizing and JPEG visualization. PSD, SVG, AI and other layered/vector assets use their supported flattened representation.
- **After (JPG preview):** The existing live composed preview from `usePreview`, with the user's current inspector settings. It is preview-quality JPEG, not necessarily the exact 96-quality final disk export.
- **3D / CAD:** Comparison is disabled because 3D viewpoints, cameras and depth cannot honestly be described as equivalent to an original 2D raster. A matched-camera 3D comparison would require a separate verified design.

## Implementation and rationale
1. The existing `_preview_worker` gains an explicit `source_only` job flag and calls `source_preview_jpeg_bytes`, which still uses `load_source_image` and its source limits.
2. The session `ThumbnailCoordinator` is parameterized for a second **1-visible / 1-retained / 850px** source view and dispatches `comparison.ready` / `comparison.failed`. It shares the supervised synchronous child render slot, executes in a background thread and cannot block the pywebview bridge. Normal gallery limits remain **16 visible / 20 retained / 192px**.
3. `DesktopApi.request_source_comparison` performs read-authorization checks for both native selected files and scanned folders. Arbitrary paths cannot confer new grants. Empty string clears wanted work; output-folder writes are not involved. Source URL remains a local loopback token, never a data URI with huge JPEG bytes.
4. The frontend hook guards against stale events and old source URLs when the active file switches, while `usePreview` now exposes the original path corresponding to the current processed preview. The control only overlays matching asset pairs.
5. The user operates a native HTML range slider (mouse/touch and keyboard arrows). Focus states and explanatory source/JPG labels are provided. The existing zoom/pan controls are hidden only while comparison is active, and all export/scanning controls remain unchanged.

## Risk, limitations and local acceptance
- [ ] `python -m ruff check previewgen/api.py previewgen/preview_coordinator.py previewgen/thumbnail_coordinator.py previewgen/renderers/pipeline.py tests/unit/test_source_comparison.py`
- [ ] `python -m pytest tests/unit/test_source_comparison.py tests/unit/test_thumbnail_coordinator.py tests/unit/test_thumbnail_api.py -q`
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] Test native Windows WebView2 and macOS Cocoa, ZIP members, PSD/SVG transparency, identical filenames from different directories, renderer missing, repeated toggles and rapid asset switching.
- [ ] Verify keyboard-only arrows/Home/End, VoiceOver/Narrator labels and focus, 1100×700 / high DPI and light/dark contrast.
- [ ] Inspect the disk/source permission boundary; ensure only the existing input grants are used, not user-supplied `file://` origins.
- [ ] Validate multiple comparisons, worker/time budgets, memory, long idle behavior and preview handle cleanup.
- [ ] Windows idle freeze issue #19 and packaging issue #22 must still be handled before release.

**No release-readiness claim:** This PR is source implementation with committed regressions, **not** a locally tested or native-verified build. Commits use `[skip ci]` as requested to preserve hosted Actions minutes.
