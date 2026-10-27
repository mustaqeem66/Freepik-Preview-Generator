# Pre-allocation boundaries for the isolated 3D depth/UV kernel

The standalone `rasterize_depth_triangles` implementation (PRs #117/#119) validates a 10,000 triangle cap and a limited pixel-work budget. It previously converted `face_colors` and `vertex_uv` into NumPy arrays *before* checking whether their first dimension matches the verified triangle count.

A malformed caller could provide just one triangle but millions of separate color or UV records, triggering avoidable allocations. This PR inserts cheap `len` count preflight for color and UV sequences, then retains the existing exact shape/numeric validation after conversion.

The change **does not** activate the kernel in the production renderer and does not implement alpha, PBR, perspective-correct UV interpolation or GPU offscreen mode. The geometry/texture bounds, default rendering output and existing source-file permission boundaries remain unchanged.

Regression tests prove that objects with million-entry lengths and bomb `__array__` methods are rejected without materialization and valid single-triangle textured rendering remains correct.

Local checks:
```bash
python -m pytest tests/unit/test_depth_rasterizer.py tests/unit/test_textured_depth_rasterizer.py -q
python -m ruff check previewgen/renderers/depth_rasterizer.py tests/unit/test_depth_rasterizer.py
python scripts/check_release_locally.py --mode full
```

Full Windows/Linux/macOS render quality, native cancellation and real authoring-app image oracles remain required under issue #60. No hosted Actions were manually dispatched; committed changes use `[skip ci]`.
