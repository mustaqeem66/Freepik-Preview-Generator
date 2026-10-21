# Reversible Focus Canvas editing mode — 2026-10-21

## Purpose

macOS desktop users often prefer to allocate most of the window to a precise visual task. Apple's [Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/) guidance encourages adjustable windows, keyboard control and personalized workspaces; [Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars) stresses deliberate, not crowded, action placement.

Inspired by content-first creative editor examples (Diffchecker images on [Dribbble](https://dribbble.com/shots/24026062-Diffchecker-image-diff)), implement a **real editing convenience** rather than merely adding more glass and colored UI chrome.

## Change and rationale

- [x] Add a Focus button in the preview's toolbar; it explicitly reveals its pressed state.
- [x] Hide the library, inspector and both resize handles while focused; expand the canvas to the main working area.
- [x] Preserve asset navigation, zoom/pan, camera interaction, single export popover, batch progress, and saved panel widths.
- [x] Make it reversible via the same toolbar button, `Alt+Shift+F` or `Escape`.
- [x] Do not hijack the shortcut inside text inputs or modal dialogs; `Escape` leaves open native/HTML dialogs alone.
- [x] Launch in the full three-pane mode every time, so first-time users do not see a mysteriously missing inspector.
- [x] Add hook tests for toggle, keyboard shortcut, input focus and modal Escape handling.
- [x] Keep current responsive layout below 851px and do not add dependencies.

## Explicit non-goals

This is not operating-system fullscreen, does not replace the native titlebar, and does not alter exported pixels, Python bridge methods, files, or selection identities. The window does not move or resize; only the React editor workspace changes.

## Verification before merge

- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] Check actual packaged Windows WebView2 keyboard and pointer behavior, native folder dialogs, split pane layout and inspector restore.
- [ ] Check macOS Cocoa/Apple Silicon, Linux GTK/Qt and high-DPI scaling.
- [ ] Check that Focus button and keyboard shortcut work with empty library, normal preview, long batch generation and 3D asset.
- [ ] Confirm `Escape` does not close a truncation acknowledgement modal or steal input focus.
- [ ] Confirm original panel width preferences and settings values persist across focus toggles.

**Status:** Source-level implementation only, draft PR; no claim of passing runtime or accessibility audit.
