# Isolated textured depth kernel — incremental UV milestone

This PR extends the bounded CPU z-buffer kernel from #117 to sample an **already-decoded, fully opaque** Pillow texture using per-vertex UVs and barycentric interpolation at the same nearest-depth pixels. The kernel supports standard repeat addressing, RGBA output and per-face color tint. Both windings are accepted.

It intentionally retains the limits from #117: at most 512×512 render output, 10,000 projected triangles, and 8 million aggregate pixel bounding-box visits. Texture dimensions must be at most 2048×2048. Non-finite UVs, missing UV/texture pair, unsupported alpha and too-large textures fail closed. No texture file reads or permission changes occur; an authorized loader must supply the decoded image.

The existing production `mesh3d.render_3d_mesh` continues to use its Painter path. **This is not production UV texture support yet:** scene/material extraction is not connected, perspective correction and normals/PBR are absent, transparent textures need a separately specified compositing contract, and actual application-produced assets with independent image references are outstanding.

## Focused regression and release handoff

```bash
python -m pytest tests/unit/test_depth_rasterizer.py tests/unit/test_textured_depth_rasterizer.py -q
python -m ruff check .
python scripts/check_release_locally.py --mode full
```

Unit checks cover multi-quadrant texture mapping, face tint, winding reversal, nontextured compatibility, missing/malformed/nonfinite UV metadata, texture bounds and alpha failure. Next milestones before runtime activation: trustworthy texture/UV extraction from real GLB/glTF/DAE/OBJ nodes; material boundaries; independently approved visual oracle dataset (#60); fixed-commit Windows/Linux/macOS timing, memory and cancellation tests. Do not claim 46/46 fidelity or production 3D completion.

**Verification:** source and regression tests authored, no complete project CI or native package testing performed; `[skip ci]` commits and no hosted Actions manually dispatched.
