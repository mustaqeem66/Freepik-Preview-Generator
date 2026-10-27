# Tiled diagonal watermark — opt-in placement

The Watermark Inspector now offers **Tiled diagonal** alongside existing Custom X/Y and object-aware corner/center positions. It is explicitly selected, never the default.

The placement value is part of the canonical `previewgen/settings_schema.json` contract and flows into the same `compose_preview` pipeline used by live preview, individual export and batch export. No separate privileged operation, filesystem read, native picker bypass, or asset mutation is introduced.

## Rendering contract
- The active watermark text, typeface, opacity, fill color and optional outline remain in effect.
- A single 25-degree rotated RGBA glyph stamp is repeated as a two-by-two or three-by-three staggered grid (at most **9 stamps**) depending on canvas size.
- Each stamp is clipped before being alpha-composited inside the existing canvas, avoiding temporary padded full-canvas rotation and bounding rendering work.
- Empty text renders no watermark and zero opacity renders a visually equivalent output to text being disabled.
- Existing position modes, coordinates, logos and default background behavior are unchanged.
- This is **not** a cryptographic watermark or a guarantee against marketplace image theft; it is a visual overlay.

## Local verification needed
```bash
python -m pytest tests/unit/test_tiled_watermark.py tests/unit/test_watermark_placement_reaudit.py tests/unit/test_settings_schema.py -q
python scripts/check_release_locally.py --mode full
cd frontend
npm run typecheck
npm test
npm run build
```

Perform visually reviewed Windows/Linux/macOS native smoke with transparent PNG, PSD, vector, 3D and batch samples before promising studio-grade output fidelity. Confirm source SHA nonmutation and cancellation. Hosted Actions were not manually triggered by this change.
