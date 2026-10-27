# GIF/WebP animated contact sheets — default-off feature and acceptance plan

**Scope:** the existing 46 direct format support claims include `.gif` and `.webp`. Previously PreviewGen Studio extracted only the first frame of animated assets. The optional `animationContactSheet` setting arranges up to nine sequential decoded frames in a square-ish grid using Pillow. It is disabled by default. The renderer keeps the source canvas dimensions and does not alter the original input file, user watermark, logo or output grants.

## Safety and format behavior

- Only native `.gif` and `.webp` sources with more than one decoded frame use this path. For all other formats—including single-frame GIF/WebP—behavior remains unchanged.
- The source raster is required to have at most 16 million pixels when this feature is enabled. Larger source canvases explicitly error in contact-sheet mode, rather than silently bypassing the limit.
- At most nine frame decodes per request; each frame thumbnail is downscaled into a bounded tile. The full sheet uses the source's original canvas W×H; the existing raster post-processing can downscale it again for output, but never upscale.
- A contact sheet is a preview of *selected temporal samples* (first nine frames), **not** a reconstruction of all animation frames or PSD/AI/CLIP/Krita artboards.
- No external artwork or codecs required beyond the existing Pillow installation. No path string from the UI gains permission; the same source-read grant applies.
- The frame sample choice is intentionally simple: first nine frames only. No frame-timing-weighted selection or animation export support is claimed.

## Verification before approving

Run against the exact PR head:

```bash
python -m pytest tests/unit/test_animation_contact_sheet.py -q
python scripts/check_release_locally.py --mode full
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

Manually preview and batch-export short/long animated GIFs and WebPs, palette/transparency/disposal combinations, single-frame inputs, 16MP+ inputs, cancellation and security checks in Windows/Linux/macOS packaged builds. Confirm default-off pixel output remains unchanged. Capture checksums and independent evidence in the local native release receipt. **Tests were authored but the full repository suites and packaged binaries were not run as part of this PR.**

Follow-ups from the user's audit that remain **not implemented** by this change: bounded `.brushset` contact sheets, Illustrator/InDesign multi-page previews, true 3D texture+depth interpolation, brand presets, and native permission-safe drag/drop.
