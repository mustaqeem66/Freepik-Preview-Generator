# PreviewGen Studio — Premium UI integration

**Status:** Proposed (PR review). **Base:** latest `main`, including merged PR #1 and PR #2. **No release published by this change.**

## Design direction

- Use calm graphite and neutral light surfaces, strong typography, clear action hierarchy, one accessible accent.
- Keep native Windows titlebar for familiar snapping, accessibility and OS window behavior. Do not replace with a frameless macOS imitation without platform tests.
- Separate sidebar/library, recessed preview and inspector through subtle materials and borders.
- Keep the existing CSS layouts, keyboard interaction, selection behavior and renderer contracts.
- Make control sizes, low-contrast labels and dense panels easier to read. Use semantic state colors only for errors/success/warnings.
- Apply blur only to small in-webview surfaces. This is not native Mica or macOS vibrancy; browsers may render differently.
- Honor reduced motion, high contrast and forced colors.

## Integrated in this change

- [x] Premium design tokens and visual treatments layered over stable existing class rules.
- [x] Batch progress and error notices moved from scattered inline styles to theme classes.
- [x] Native folder picker explanation and completed-but-empty folder scan message.
- [x] Optional desktop toast when a batch finishes, with bounded subprocess execution and failure handling.
- [x] Desktop notification opt-in persisted in the canonical settings contract (default **off**).
- [x] Preserve operation-id filtering and bounded batch event payloads from previous reliability work.
- [x] Keep installer filename `PreviewGen-Setup.exe` compatible with current `install.ps1`.
- [x] Add Start Menu AppUserModelID hint to support Windows notifications where the OS allows it.
- [x] Add regression tests for notification process failures and bridge isolation.
- [x] Raise functional label text to 12px, keep 10-11px for short badges only, enlarge swatch and preset hit targets, and honour `prefers-reduced-transparency`.
- [x] Remove dead batch callback globals and document indeterminate discovery progress.
- [x] Replace unmeasured speed, frame-rate, ZIP-recursion, ICC and palette claims in the README with tested behaviour.

## 2026-11-21 — Accessibility audit of the running app

Ran axe-core 4.13.0 against the production bundle in a real browser engine, in
both light and dark themes. Found and fixed:

- **Invalid ARIA (critical).** The asset listbox carried `aria-rowcount` on
  `role="listbox"` and `aria-rowindex` on `role="option"`. Those are grid-only
  attributes; ARIA 1.2 uses `aria-setsize`/`aria-posinset` on the options.
  axe-core rejected five nodes. Removed the grid attributes and updated the
  screen-reader regression test to assert the ARIA 1.2 contract.
- **Insufficient colour contrast (serious).** The format badge used
  `opacity: 0.6` on `var(--text-muted)`, which dims the foreground against the
  surface and measured 3.91–4.21:1 — below the 4.5:1 WCAG AA floor. Replaced
  the opacity overlay with the `var(--text-sec)` token, whose contrast is
  guaranteed against the surface.
- **Scrollable region not keyboard reachable.** The library and inspector
  panes scroll independently but were not focusable, so a keyboard user could
  not scroll them. Both are now `tabIndex={0}` with a visible focus ring.

After the fixes, the axe audit reports **0 violations** in both light and dark
themes. The two remaining "incomplete" axe items are items that require a
human judgement (such as whether a live region is announced as intended),
not failures.

## Not integrated from the older ZIP

- The ZIP's `previewgen/api.py` is from an older baseline. Replacing the current file reintroduces lifecycle and overwrite bugs.
- The ZIP's versioned setup artifact rename is incompatible with the current PowerShell installer.
- The ZIP's automated success claims do not establish actual notification presentation on Windows/macOS/Linux.
- Do not publish a new version based solely on ZIP's reported pass counts.

## Remaining work before release

1. Run Python lint and tests, frontend typecheck/tests/build, and settings contract generation check in CI.
2. Test Windows actual foreground/background notification display on a clean install with Start Menu shortcut and notifications allowed/denied.
3. Validate native Setup wizard, custom directory, desktop icon and uninstall after fresh installation and upgrade.
4. Test UI at 100/125/150/200% scaling, light/dark themes, high contrast and reduced motion.
5. ~~Implement real **Add Files** support end-to-end~~ — **done.** The native multi-select picker, per-file preview, batch export and exact-path authorization are implemented and covered by `tests/integration/test_native_picker_linux.py` and the unit-level grant tests.
6. ~~Follow up with resizable panels, command palette, thumbnail browser~~ — **done.** `PaneResizer`, `CommandPalette` and the bounded `AssetGallery` thumbnail browser are all implemented; the thumbnail path is served by `DesktopApi.request_thumbnails` with a visible-window budget and per-request generation guards so a stale response cannot overwrite a newer one.
7. Do not state that SmartScreen warnings are eliminated by scripts or checksums; use trusted code signing.

## Distribution contract

| Channel | Install wizard | Install path | Shortcuts | Updates |
| --- | --- | --- | --- | --- |
| `PreviewGen-Setup.exe` (Inno Setup) | Yes | Choose in wizard | Start Menu + optional Desktop | Manual new installer |
| PowerShell `install.ps1` on `main` | Yes (opens above setup) | Choose in wizard | Installer-managed | Latest published release at invocation |
| Portable Windows ZIP | No | Extract anywhere | Optional helper batch | Manually download new ZIP |
| macOS DMG / Linux AppImage | Platform-specific | Platform-specific | Platform-specific | Manual as currently packaged |

The ZIP was built from another source snapshot. Always develop feature changes on the current GitHub `main`, preserving the merged backend fixes.

## 2026-10-21 — Searchable asset browser (proposed PR)

- [x] Add filename search without copying the complete asset list when the search is empty.
- [x] Keep original source indices for selection and export; a filtered result cannot silently retarget a different file.
- [x] Keep `aria-activedescendant` referencing an existing option even when that option is outside the current virtual window.
- [x] Support a no-matches state and filtered keyboard navigation.
- [x] Add regression cases for searching, original-index selection, zero results and virtualized active descendants.
- [x] Locally run `cd frontend && npm ci && npm run typecheck && npm test && npm run build`.
- [ ] Verify real WebView2 scrolling and screen-reader behavior; source-level semantics alone are not an accessibility certification.
- [x] Add thumbnail browser as a separate opt-in implementation after backend thumbnail budget and cache limits are designed.
