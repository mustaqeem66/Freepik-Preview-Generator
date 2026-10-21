# Studio UI refinement — compact export dock and precision sliders

**Date:** 2026-10-21  
**Trigger:** Screenshot feedback on overly wide, detached Batch export footer; unwanted header Commands/Diagnostics buttons; native blue inspector sliders feel inconsistent with a premium light/dark interface.

## What changed and why

1. **Repositioned Batch export.** The old `studio-footer` rendered as a separate full-window horizontal row below the three-pane workspace, disconnected from the canvas. It is now a compact `CanvasExportDock` in the **center preview pane**, directly below the artwork footnote. The Batch export status, Generate Previews/Cancel Batch, progress, errors, truncation warnings and Open output action remain grouped near the preview and its export-size control. Library and inspector retain their own scroll areas. At narrower window widths the dock wraps instead of squeezing buttons into a tiny strip; the outer window no longer reserves a full-width footer.
2. **Simplified toolbar.** Removed the *visible* Commands and Diagnostics buttons, preserving compact brand, lifecycle, settings persistence/retry and light/dark appearance. The existing `Ctrl+K` / `⌘K` shortcut still opens Quick actions, including **Open local diagnostic logs** for advanced troubleshooting. We did not remove backend diagnostics or break observability for unresolved Windows idle-hang investigation #19.
3. **Redesigned sliders.** All inspector sliders use a real semantic HTML range input with a soft, inset track and dark concentric circular thumb inspired by the user's reference. Values retain `min`, `max`, steps and onChange semantics; foreground fill is computed from normalized percent including nonzero and negative ranges (e.g. fontScale 20–300, pitch -85–85). Color tokens are defined for **both light and dark** and use a deliberately neutral charcoal/ivory emphasis rather than a bright blue handle. Selected scale/opacity sliders have unobtrusive lower/middle/higher contextual hints.
4. **Accessibility and compatibility.** Keyboard arrow/Home/End still use the browser's real slider behavior; visible focus-within ring, accessible label, high-contrast native fallback, reduced-motion handling, tooltip/title elsewhere, and tests. No external slider library, fonts, image hosts, or fake native window chrome.

## Source locations
- `frontend/src/App.tsx`: toolbar controls and placement of CanvasExportDock beneath canvas.
- `frontend/src/components/CanvasExportDock.tsx`: reusable export action group, including disabled output state.
- `frontend/src/components/BatchProgress.tsx`: compact status/action layout retaining progress, cancellation, warnings.
- `frontend/src/components/SettingsPanel.tsx`: native slider markup and percentage formula.
- `frontend/src/studioControls.css`: responsive dock and theme-aware range styling, loaded last in `main.tsx`.
- Component tests for BatchProgress, CanvasExportDock and SettingsPanel.

## Local quality gates (not performed by this source-only authoring session)

```powershell
cd frontend
npm ci
npm run typecheck
npm test
npm run build
cd ..
python scripts/check_release_locally.py --mode full
```

Native Windows WebView2 / macOS Cocoa QA: verify 1100×700 and larger windows, both light/dark, 100/125/150/200% DPI, full-width Focus Canvas, Batch export idle/running/cancellation/error, Open output authorization, precise keyboard slider movement and focus; check a real screen reader and forced-colors. For Ubuntu/Linux, a missing `xdg-open` previously produced `[Errno 2]` as shown in the screenshot. `DesktopApi.open_folder` now falls back to `gio open` where installed; if neither exists it returns the explicit `NO_FOLDER_OPENER` response. The same existing authorization checks remain in place. Tests cover the fallback, missing opener and unauthorized path. Some minimal Linux systems still need `xdg-utils` or a GLib/GIO file manager installed. Diagnostics remain reachable via Quick actions and local logs.

**Tests added, not claimed passed.** Commits use `[skip ci]` because hosted Actions minutes are exhausted. No hosted workflow was intentionally triggered.
