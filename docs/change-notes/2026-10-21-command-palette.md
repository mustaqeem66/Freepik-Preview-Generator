# PreviewGen Studio keyboard command palette — 2026-10-21

## Why
Apple's macOS HIG recommends discoverable keyboard shortcuts and productivity features without excessive navigation chrome: https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/
Our independent Dribbble/Behance design research and original design decisions are recorded in `docs/design/2026-10-21-macos-premium-ux-research.md` (merged PR #32).

## Functionality
- A visible Commands control opens a keyboard-first search dialog. `⌘K` on macOS and `Ctrl+K` on Windows/Linux while app has focus.
- Search command titles, groups and keywords; navigate with Up/Down, invoke with Enter, dismiss with Escape, and keep Tab focus within Search/Close.
- Restore the prior focus target, expose selected/disabled states, and handle forced colors/reduced transparency.
- Reuse existing guarded handlers for folder selection, scan, asset navigation, single JPG, batch, opening output, Focus Canvas, appearance and diagnostics.
- No new backend APIs, permissions, external fonts or artwork; unavailable actions remain disabled.
- The palette does not promise native menu-bar commands, OS-global keyboard shortcuts or native AppKit vibrancy.

## Local acceptance
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`.
- [ ] macOS `⌘K`, Windows `Ctrl+K`; verify with text input focused and Focus Canvas enabled.
- [ ] Keyboard-only + VoiceOver/Narrator; confirm Escape does not trigger Focus Canvas.
- [ ] Backend disconnected, partial scan without acknowledgement, batch running, empty selection.
- [ ] 1100×700, high-DPI, light/dark, forced colors, reduced transparency.
- [ ] Verify actual native packaged WebView; no merge/release readiness claims based on mocked tests.

The work is proposed in a draft PR, with `[skip ci]` to conserve hosted Actions minutes.
