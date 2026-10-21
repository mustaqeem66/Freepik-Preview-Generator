# 2026-10-22 — Preview renderer capability inventory and fidelity evidence (#60)

## Why

The registered extensions include full raster/vector decoders, a software 3D mesh pipeline, CAD-to-mesh conversion, proprietary embedded thumbnails, and external Blender fallback. Calling them all generically “supported files” implies a reliability guarantee the code cannot make. Actual release fixture tests cover only nine examples; they cannot certify versions and complex scenes for the other advertised extensions.

## Implemented

1. Added `previewgen/renderers/capabilities.py`, a **complete 47-extension catalog** with one explicit per-extension preview mode, human-readable description, engine dependencies and known limitations. A registry test fails if a newly advertised extension lacks capability metadata (or a catalog entry is unregistered).
2. The existing isolated metadata probe returns `previewSupport`, and the Inspector shows an unobtrusive caveat for conditional, embedded, fallback and CAD preview modes. Ordinary rasters/vectors/meshes remain visually quiet.
3. Added a provenance-aware manifest `tests/fixtures/renderer-samples.json` listing **the nine actual existing fixtures only**; it intentionally does not fabricate proprietary samples.
4. Added `scripts/audit_renderer_matrix.py`. By default it creates a local JSON coverage inventory (explicit absent-format list) and returns success only if the **catalog itself is consistent**, not by claiming all formats are verified. `--verify-fixtures` uses real isolated render workers, JPEG output-content checks and original-source SHA-256 verification, returning a non-zero code for missing/broken fixtures. `--strict` fails unless **every advertised previewable extension** has a present fixture, even when no render is requested.
5. Integrated the inexpensive inventory into local full release checks; strict full-matrix verification remains a separate gate until the missing legitimate sample files can be supplied. Results are gitignored and never uploaded by default.

## Local execution

```bash
python -m pytest tests/unit/test_renderer_capability_matrix.py -q
python scripts/audit_renderer_matrix.py
python scripts/audit_renderer_matrix.py --verify-fixtures
python scripts/audit_renderer_matrix.py --verify-fixtures --strict
python scripts/check_release_locally.py --mode full
```

The last strict audit is **expected to fail right now**, because most proprietary file fixtures do not exist in this repository. Do not interpret a passing non-strict inventory as proof that all files preview correctly. The report enumerates missing coverage. For real source-app/version acceptance tests, add consented/licensed filenames and the actual software version to the sample manifest, and record expected dimensions or human-reviewed oracle screenshots outside the repository as permitted.

## Remaining scope

- Full DWG geometry rendering is not implemented; DWG requires an embedded preview. MAX/MA/MB/F3D, INDD, Affinity, Procreate and several others also have embedded-preview/version constraints. BLEND fallback needs Blender installed; STEP/IGES conversion needs cascadio/trimesh; DXF needs ezdxf/matplotlib. A proprietary format may be recognized yet legitimately unable to render.
- Validate both 2D/3D/CAD user-owned fixtures under Windows WebView2, macOS Cocoa and Linux GTK/Wayland with dependency versions, crash/timeout/memory behavior, exact preview accuracy and screenshot review. Catalog metadata by itself is not a decoded-file audit.
- Continue issue #60 until all agreed format/version acceptance criteria are satisfied; do not close #19 Windows idle-hang or #22 production release gates based only on fixture inventories.

**Source and unit tests created, not executed in this authoring environment. Commits include `[skip ci]` and do not request hosted GitHub Actions.**
