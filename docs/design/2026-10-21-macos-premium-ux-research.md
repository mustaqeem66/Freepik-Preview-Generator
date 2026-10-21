# PreviewGen Studio — Premium macOS UI research and implementation brief

**Date:** 2026-10-21
**Scope:** Study Dribbble and Behance concepts, check against Apple's macOS design guidance, compare with PreviewGen's actual React/pywebview frontend, and implement original cross-platform design decisions. This document is not a claim of Apple's endorsement or of a native AppKit application.

## Source-backed observations

| Reference | Relevant pattern | Practical implication for PreviewGen |
| --- | --- | --- |
| Apple, Designing for macOS — https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/ | Large workspace, resizable windows, keyboard and precision input, menu commands | Maintain the native title bar, preserve resizable panes, offer discoverable shortcut actions |
| Apple, Sidebars — https://developer.apple.com/design/human-interface-guidelines/sidebars | Keep navigation concise; allow sidebar customization/hide when helpful; do not bury critical controls at bottom | The asset library should read as navigation, and controls should remain accessible during resizing |
| Dribbble, Nixtio 3D Editor (Jan 2026) — https://dribbble.com/shots/27016525-3D-Editor-App-UI-Creative-Design-Tool | Dark editor layout, object scaling and color editing | Recess utility chrome and emphasize the preview/inspector |
| Dribbble, Alex Void Hints desktop redesign — https://dribbble.com/shots/23679964-Remake-of-Hints-Desktop-app-Home | Converted mobile action panel into a desktop sidebar and kept editor visible | Avoid modal page navigation for routine edits; keep list, preview and inspector together |
| Dribbble, Robert Licau macOS mail light (Sep 2026) — https://dribbble.com/shots/27764997-Desktop-email-app-for-macOS-light-mode | Three-pane, adjacent editor, quiet light theme | Keep three-pane density and quiet backdrop rather than stack dashboard cards |
| Behance, Hamid Jay AI Image & Video Enhancer macOS (Feb 2026) — https://www.behance.net/gallery/243509671/AI-Image-Video-Enhancer-for-macOS-UIUX-Case-Study | Light/dark presentation, simple enhancement workflows, before/after exploration | Clear preview state and tool grouping; comparison view belongs in a separate verified phase |
| Behance, Codesign macOS Design System — https://www.behance.net/gallery/105765193/Codesign-macOS-App-Design-System | Design-system framing for editor controls | Centralize design tokens, do not duplicate ad hoc widget styles |
| Behance, Acronis Desktop App Design — https://www.behance.net/gallery/92029555/Acronis-Desktop-app-design | Desktop day/night modes and approachable file workflows | Preserve PreviewGen's persisted theme and filesystem clarity |

**Boundary:** These are portfolio concepts and examples, not proof of usability testing or production quality. Implementation decisions below are our synthesis, not a claim that any featured designer recommends PreviewGen's specific colors or dimensions. No portfolio imagery, icons, typography files, or code is copied.

## Assessment of merged PreviewGen frontend

At the reviewed main branch the frontend already includes: a three-pane library / preview / inspector layout, locally remembered pane widths, search over a virtualized asset list, transparent-light/dark CSS materials, 3D orbit, fitted preview zoom/pan, batch progress and local-only processing. Keep these working features and their bridge contracts intact.

Observed design issues:
- Dense layered CSS overrides in `index.css` make visual hierarchy less predictable.
- The glossy primary-button gradient and multiple competing shadow depths distract from the artwork.
- Tiny contextual labels, similar-weight panels and a boxy header reduce hierarchy.
- Existing rounded corners, translucency and shadows are *CSS*, not real native macOS vibrancy.
- The main workspace and canvas can be more distinct without hiding critical tool affordances.
- A desktop command-palette / shortcut affordance is absent. That belongs to the subsequent keyboard-interaction PR.

## Design decision record (why, what, trade-off)

1. **Quiet window chrome:** Native titlebar stays untouched for Windows window snapping and macOS traffic lights. Brand and backend status remain visible.
2. **Artwork-first center canvas:** Recess canvas frame and side panels; subtle crosshatch is optically quiet, not a printed checkerboard or preview content.
3. **Controlled tonal palette:** Retain existing system-font stack; use existing color variables and fewer saturated fills. Contrast remains functional in dark/light themes.
4. **Measured elevation:** One major workspace shadow; smaller button and preview shadows. No heavy glowing gradients or fake frosted glass.
5. **Precise but approachable controls:** Consistent 34–37 px action heights, visible focus states, subtle active states, accessible labels.
6. **No image assets or new runtime dependencies:** All styling in `studioPolish.css`, imported after the baseline stylesheet. Easy to revert.
7. **Respect accessibility:** Preserve reduced-motion, reduced-transparency and forced-colors behavior. Do not animate layout or change interaction timing.
8. **No fake native claims:** pywebview remains cross-platform HTML/CSS UI; future AppKit integration is a separate engineering project.

## Staged roadmap

- **PR stage 1 (this PR):** Original visual refinement in one CSS layer, with documented sources and manual acceptance criteria.
- **Stage 2:** Keyboard-first command palette with `⌘K` on Mac, `Ctrl+K` on Windows/Linux, arrow navigation and Escape.
- **Stage 3:** Explore real multi-file import, thumbnail gallery with memory budget, before/after comparison, collapsible inspector and source-file selection safeguards.
- **Stage 4:** Native Mac smoke + color/scale/accessibility verification; Windows WebView2 compatibility before any release claim.

## Acceptance checklist before merge

- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] Mac and Windows native packaged preview, source picker, batch, inspector and zoom smoke.
- [ ] Light/dark at 100%, 125%, 150%, 200% DPI; 1100×700 and larger windows.
- [ ] Inspect focus rings, VoiceOver/keyboard navigation, high contrast, reduced transparency, reduced motion.
- [ ] Confirm editable fields, menus, export popover and native window controls remain operable.
- [ ] No GPU memory increase or WebView2 freeze recurrence in a long idle session.

**Verification:** New CSS is source-level only; no CI or native runtime test was executed while creating this PR.
