# Opt-in transparent subject framing

**Default:** disabled. No change to existing images or legacy export settings.

When enabled in the Studio Background inspector, `autoFrame` normalizes the source's visible alpha bounding box within the **original canvas dimensions**, respecting the selected `frameMargin` (0–25% of each edge). It does not edit the original file. The same validated settings flow into live preview and batch/single JPG composition.

Behavior and limits:
- Ignore alpha values <=8 for bounding-box detection (avoids tiny antialiased halos).
- Recenter the subject on a transparent canvas; preserve subject aspect ratio and original W×H.
- For a very small sprite, never magnify more than 4x. Some target margins will remain larger than requested; this is an intentional artifact-quality limit.
- Fully opaque files skip normalization. Completely transparent images retain the prior explicit error.
- Does not crop the output image, override user watermark/logo settings, read any extra files or bypass picker grants.
- May enlarge decoded bitmap pixels; this opt-in is appropriate for transparent asset packs, not required for exact-pixel fidelity work.

Validation still required: local targeted tests, frontend TypeScript/Vitest/build, native Windows/Linux/macOS before-and-after composition, raster/PSD/SVG/3D samples and full renderer oracle evaluation.

```bash
python -m pytest tests/unit/test_auto_frame_subject.py tests/unit/test_settings_schema.py -q
cd frontend && npm run typecheck && npm test && npm run build
```
