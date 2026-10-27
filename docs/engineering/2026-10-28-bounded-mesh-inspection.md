# Mesh preflight bounded-read remediation — 28 October 2026

## Re-verified source gap
The 27 October audit's unbounded Maya line-read issue was addressed earlier, but inspection of current `previewgen/limits.py` revealed related remaining pre-parse allocation risks:
- OBJ and ASCII STL complexity estimators iterate unbounded binary lines, so a malformed one-line file can be loaded into memory before the worker rejects it.
- PLY header estimator calls unrestricted `readline()`.
- GLB estimator `read(chunk_length)` buffers binary chunks it never examines; a malformed or very large chunk could impose unnecessary allocations. The `.gltf` JSON estimator also loads an entire input document without a dedicated metadata cap.

## Proposed source fix (this PR)
- Limit every OBJ, ASCII STL and PLY inspection line to 256 KiB, with a clear hard failure for out-of-budget lines.
- Prevalidate GLB chunk lengths against remaining file size; skip non-JSON binary chunks with `seek` without loading them into Python; cap JSON inspection chunks to 64 MiB.
- Bound external `.gltf` JSON documents to 64 MiB before decoding.
- Preserve ordinary mesh vertex/face estimates; existing geometry and renderers are not changed.
- Tests cover long-line rejection, valid OBJ/PLY/STL/glTF, truncated GLB, oversized JSON, and non-JSON GLB skipping.

The limits are intended as conservative fail-closed parsing budgets, not arbitrary 3D fidelity guarantees. Rare legitimate glTF files with >64MiB metadata or >256KiB single lines now explicitly fail instead of using unbounded allocations. This is a source-level preflight hardening change; it does **not** imply issue #60 visual-oracle or issue #22 packaged-native release certification.

## Local owner gate
```bash
python -m pytest tests/unit/test_mesh_inspection_read_bounds.py tests/unit/test_resource_limits.py -q
python scripts/check_release_locally.py --mode full
```

Then exercise malformed and valid OBJ, STL, PLY, GLB and glTF through the installed Windows/Linux/macOS app and verify error reporting and safe cancellation. No hosted GitHub Actions were manually invoked.
