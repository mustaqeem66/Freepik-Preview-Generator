# Canvas magnification and pan — 2026-10-21

## Why
Creators could view only a fitted JPEG. Fine watermark placement and tiny design details were difficult to inspect.

## Changes
- Zoom the displayed preview from fitted baseline (100%) to 400% in 25% steps.
- Drag to pan a magnified 2D preview; keep existing 3D orbit gestures separate.
- Provide accessible zoom in, zoom out and fit controls with clear magnification semantics.
- Reset zoom/pan on every new preview URL to avoid stale transforms when selecting another asset.
- Include a targeted frontend UI regression.

## Scope
This is viewport magnification of the **rendered JPG** (not a new high-resolution re-render, and not a promise of 1:1 source pixels).
It does not modify output files, metadata, rendering, source authorization or export sizing.

## Verification
- [ ] cd frontend && npm ci && npm run typecheck && npm test && npm run build
- [ ] Check Windows WebView2 pan, 3D orbit, pointer capture, keyboard controls and DPI.
- [ ] Check overlapping canvas hints and progress notifications at small widths.
