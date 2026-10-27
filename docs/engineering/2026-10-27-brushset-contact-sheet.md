# Procreate brushset multi-tip contact sheets

27 October 2026 — review draft.

**Default remains unchanged:** a .brush or .brushset shows its saved preview/first available tip. Enabling brushsetContactSheet in the Inspector displays a fixed 1–9 nested .brush tip grid, selected from the user's already-authorized .brushset archive. It never uses local paths from inner archive metadata as filesystem reads and never changes the source.

Every .brush archive is routed through the existing capped ZIP validator; the outer .brushset also passes open_zip_bounded. The parser reads **at most nine** nested brushes. Invalid inner archives fail explicitly rather than inventing partial preview success. No extra binary decoders or network calls are introduced.

The contact-sheet canvas is capped to 2400×2400 RGBA; it respects smaller requested dimensions down to a minimum 240px. Only enabled .brushset sources use this path; unrelated creator/brush, GIF, WebP, image, 3D, CAD and batch formats keep their existing behavior.

Local checks, separately from the still-required native packaged acceptance:

```bash
python -m pytest tests/unit/test_brushset_contact_sheet.py tests/unit/test_creator_security_reaudit.py -q
python scripts/check_release_locally.py --mode full
cd frontend && npm ci && npm run typecheck && npm test && npm run build
```

Run real saved Procreate brushsets with 1, 4, 9, >9 tips, damaged archives, thumbnail fallbacks and cancellation on actual Windows/Linux/macOS packaged builds. This PR includes synthetic ZIP fixtures and regression tests, not independent Procreate-version visual oracles; keep issue #60 open. Native security acceptance (#59) remains outstanding.
