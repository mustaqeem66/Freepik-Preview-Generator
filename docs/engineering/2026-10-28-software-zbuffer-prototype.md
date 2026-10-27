# Isolated depth-buffer rasterization correctness milestone

The former mesh renderer's average-face-depth Painter sorting produces invalid occlusion for intersecting triangles. This PR introduces `previewgen/renderers/depth_rasterizer.py`: a separate CPU orthographic z-buffer kernel. It rasterizes at pixel centers, interpolates per-pixel depth via barycentric weights, preserves both triangle windings, rejects non-finite geometry/colors, and stores the **nearest surface for each output pixel**, independent of triangle submission order.

## Explicit bounds and limitations

- Maximum canvas **512 × 512**; at most **10,000** projected triangle faces; at most **8,000,000** aggregate bounding-box pixel visits per invocation.
- RGBA output, opaque triangle RGB shading only, no transparency or texture lookup.
- Depth convention: higher z closer to the virtual orthographic camera; the caller must supply projected `(x_px, y_px, z)` vertices already transformed to that convention.
- No external file reads, no filesystem permissions, no new dependencies beyond existing NumPy/Pillow.
- **Not activated in `mesh3d.render_3d_mesh` yet.** It is deliberately isolated until an independently approved visual-oracle corpus can prove that pixel depth, normals, UV sampling, clipping, and native packaged performance meet release requirements. The current production renderer remains Painter-based.
- Not PBR: no normals interpolation, UV sampling, transparent-material ordering, roughness/metalness or ambient occlusion. Do not close issue #60 merely for this kernel.

## Targeted tests

```bash
python -m pytest tests/unit/test_depth_rasterizer.py -q
python scripts/check_release_locally.py --mode full
```

Test cases assert front-face wins under reversed submission order, reversed face winding, depth crossovers within the same two projected triangles, degeneracy, non-finite coordinates, out-of-range colors and over-budget denial.

Follow-up independent PRs: per-node UV/textured visuals retained before scene combining; sampled texture color through interpolated barycentrics; separation between opaque and alpha-blended faces; bounded integration behind an opt-in; reviewed image-oracle fixtures and native Windows/Linux/macOS packaging proof. No claim of end-to-end 3D fidelity is made.

**Verification:** Source/test files authored. Full project and native CI must be run by the owner; GitHub Actions not manually triggered. Commits include `[skip ci]`.
