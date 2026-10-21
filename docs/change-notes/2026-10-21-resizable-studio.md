# Resizable PreviewGen Studio panels — 2026-10-21

## Why
Fixed side-panel sizes unnecessarily constrain large canvases and make the asset list or inspector difficult to use in different workflows.

## Change
- Add keyboard-accessible, pointer-draggable separators for the asset library and inspector.
- Respect minimum/maximum widths, with a minimum canvas width.
- Persist pane widths in local WebView storage while tolerating storage failures.
- Preserve compact responsive layouts under 851px with no visible resizers.
- Add tests for keyboard direction, clamping and reset.

## Validation
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] Check Windows WebView2 pointer-capture and focus navigation.
- [ ] Check 100/125/150/200% DPI, dark/light themes and high contrast.
- [ ] Check dragging during 3D render and scanner activity.

This PR changes neither renderer nor Python backend behavior. No CI or native runtime verification was performed in this connected session.
