# Renderer audit: raster imports and source preservation

Date: 2026-10-21

## Confirmed defects
1. The canonical scanner/picker/batch registry was missing JPG, JPEG, BMP, GIF, and ICO despite all five being decoded by the existing Pillow loader and already listed in raster resource-limit checks. Consequently a JPEG-only folder could appear empty in the asset sidebar.
2. When JPG input and output share a folder, `image.jpg` can equal the original source. The overwrite policy could then replace an input. A PNG and a JPG with the same stem create the same danger if one export targets the other source file.

## Implemented repair
- Register the already-supported raster types in `SUPPORTED_EXTENSIONS` so scanner, selected-file picker, ZIP inspection, and batch discovery agree.
- Add `protect_source_destinations` to the destination module. Batch output planning protects **every work-item source**, not only the current input; single export protects its source. If a generated JPG target would hit an original file, create an unused `_preview` target even under the overwrite policy.
- Tests exercise raster decoding, the reserved-path allocator, JPEG same-folder export and a mixed PNG/JPG batch, with immutable original hash checks.

## Verified scope vs. remaining limitations
No code change can guarantee every producer/version of a proprietary binary preview format. Supported extension means an attempt is implemented, not that every file contains a decodable thumbnail.

- DWG: embedded thumbnail only; no full arbitrary DWG geometry reconstruction. DXF: requires ezdxf/matplotlib.
- STEP/STP/IGES/IGS: cascadio plus trimesh conversion required, native CAD fidelity varies.
- BLEND: saved thumbnail or external installed Blender in script-disabled mode; not a general interactive native Blender viewport.
- MAX/F3D/MA/MB/INDD/Affinity/Procreate/CLIP: embedded/flattened preview extraction and compatibility limits, not guaranteed full native editing format decoding.
- OBJ/GLB/GLTF/STL/PLY/3MF/DAE: software rasterized 3D triangulation; complex scenes, textures, material support and animations can differ from the authoring application.
- SVG/AI/EPS: SVG uses resvg; AI/EPS may require PDF-compatible export or embedded thumbnail.
- PSD: composite flattening, not editable per-layer fidelity.

## Next validation gates
Run locally: `python -m pytest tests/unit/test_raster_source_safety.py -q`, `python -m ruff check previewgen/config.py previewgen/destinations.py previewgen/api.py previewgen/batch/runner.py tests/unit/test_raster_source_safety.py`, `python scripts/check_release_locally.py --mode full`.
Then test real application-produced samples of all 2D, 3D and CAD formats on Windows/macOS/Linux with the relevant renderer dependencies installed. Verify hash-preservation on sources and exported JPG contents. Keep existing P0 release issues open until native evidence passes.

Status: committed source changes and regression tests; not a validated bug-free product.
