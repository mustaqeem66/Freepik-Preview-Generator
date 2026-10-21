# PreviewGen Studio — premium macOS-informed interface audit (2026-10-21)

## Context and scope

PreviewGen is a React + pywebview **cross-platform desktop editor**, not a native AppKit/SwiftUI window. Its core content is user artwork, not a dashboard. The design must retain the native titlebar, existing renderer, folder security, asset selection, panel widths, keyboard semantics, batch controls and light/dark themes.

This document distinguishes **portfolio visual references** from **Apple product guidelines**. Portfolio shots suggest patterns, not evidence of native platform accessibility or working functionality.

## Research corpus

### Authoritative Apple guidance (2026)

- Designing for macOS: https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/
  - High-resolution display, precise pointer interaction, keyboard shortcuts and long-running workspace sessions; resizable/customizable windows.
- Toolbars: https://developer.apple.com/design/human-interface-guidelines/toolbars
  - Clear leading/center/trailing groupings; avoid a crowd of equally prominent actions and indiscriminate tinted backgrounds.
- Sidebars: https://developer.apple.com/design/human-interface-guidelines/sidebars
  - Favor hide/show controls, succinct group labels and simple structure. Don't hide critical commands at the bottom of the window.
- Layout: https://developer.apple.com/design/human-interface-guidelines/layout
  - Consistent geometry, negative space and progressive disclosure. Keep the content prominent.
- Materials: https://developer.apple.com/design/human-interface-guidelines/materials
  - Glass/material is for navigation/control layers, not everywhere and not painted into the artwork/content layer.

### Dribbble (visual and interaction references)

- Diffchecker image comparison: https://dribbble.com/shots/24026062-Diffchecker-image-diff
  - Work-focused dark canvas, compact comparison mode controls, content-first workflow. Inspiration for later before/after support.
- Diffchecker desktop images: https://dribbble.com/shots/6088050-Diffchecker-Images-Comparision-Tool
  - A dedicated desktop utility instead of a web-style metrics dashboard.
- Blitzit Tower for macOS (Sept 2026): https://dribbble.com/shots/27773123-Blitzit-Tower-UI-for-macOS-Sidebar-Navigation-and-Timer
  - Small footprint, strong continuity with the full workspace and compact navigation.
- Meng To sidebar: https://dribbble.com/shots/17692245-Sidebar
  - Sidebar proportions and visual treatment suitable for a large app, not proof of native controls.

### Behance (visual references, historical concepts)

- Acronis desktop UI (2020): https://www.behance.net/gallery/92029555/Acronis-Desktop-app-design
  - Legible list selection, sparse utility surfaces and complementary light/dark schemes.
- Behance Studio macOS concept (2017): https://www.behance.net/gallery/57657627/Behance-Studio-Branding-macOS-UIUX-Design
  - Restrained dark palette, visible primary action, navigable recent-project structure.
  - **Historical concept only**; should not be copied as current 2026 macOS chrome.

## Design decisions and reasons

| Decision | Reason | Implementation |
| --- | --- | --- |
| One quiet accent | Artwork must dominate, not colored chrome | Focus ring/selection/primary button only |
| Neutral paired light/dark surfaces | Clear hierarchy without deep black-on-black or muddy midtones | Semantic CSS surface tokens |
| Canvas with subtle grid texture | Disambiguates neutral preview space without leaking into exported JPG | CSS background on preview surface only |
| Simpler chrome and restrained controls | Users work for hours; avoid ornamental effects and multiple gradients | Flat primary action, unified radii/borders |
| Stronger navigation state | Selected file is source of truth for preview/export | Selection contrast and list treatment |
| Legible labels and focus | Pointer plus keyboard use on Mac/Windows | Preserve 12–13px functional labels, visible focus rings |
| Preserve native titlebar | Correct Windows snap/macOS familiar controls and accessibility | No fake traffic-light buttons |
| Avoid global animation on rendered image | Existing zoom/pan uses CSS transforms | Remove preview-entry transform animation |
| Respect user accessibility preferences | Reduce distracting motion/translucency | Reduced transparency/motion, contrast and forced-color overrides |
| Separate responsive behavior | Real utility windows vary in width | Existing 1100/850/560 layout breaks unchanged |

## Current PR implementation

- [x] Add a late-loaded stylesheet that improves visual materials without rewriting `index.css` or changing state/backend contracts.
- [x] Leave current resizable panes, input/output selection, asset virtualization, zoom, export reporting and native titlebar intact.
- [x] Keep the preview image transform under the zoom/pan feature's ownership.
- [ ] Run `cd frontend && npm ci && npm run typecheck && npm test && npm run build`.
- [ ] Real Windows WebView2, macOS Cocoa and Linux GTK/Qt visual review at 100/125/150/200% scaling.
- [ ] Test light/dark, forced colors, reduced transparency/motion, 1100/850/560px window widths and 3D preview.
- [ ] Capture and review real screenshots with the app running. This source-only implementation is **not** a native screenshot verification.

## Next separate implementation

Add reversible, keyboard-accessible **Focus Canvas** mode for editing at maximum size. Native multi-file import, lazy thumbnail generation and before/after comparison remain independent substantial features, not decorations to fake in CSS.

## Release safeguard

This is macOS-*informed*, not native Liquid Glass, Mica, Apple proprietary materials, or exact reproduction of any designer's work. No outside images, icons, libraries or branding have been copied into this repository.
