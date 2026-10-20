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
5. Implement real **Add Files** support end-to-end (native multi-select, preview, batch, security authorization) in a separate PR. A folder picker correctly hides files; its hint is not a substitute.
6. Follow up with resizable panels, command palette, thumbnail browser and stronger accessibility.
7. Do not state that SmartScreen warnings are eliminated by scripts or checksums; use trusted code signing.

## Distribution contract

| Channel | Install wizard | Install path | Shortcuts | Updates |
| --- | --- | --- | --- | --- |
| `PreviewGen-Setup.exe` (Inno Setup) | Yes | Choose in wizard | Start Menu + optional Desktop | Manual new installer |
| PowerShell `install.ps1` on `main` | Yes (opens above setup) | Choose in wizard | Installer-managed | Latest published release at invocation |
| Portable Windows ZIP | No | Extract anywhere | Optional helper batch | Manually download new ZIP |
| macOS DMG / Linux AppImage | Platform-specific | Platform-specific | Platform-specific | Manual as currently packaged |

The ZIP was built from another source snapshot. Always develop feature changes on the current GitHub `main`, preserving the merged backend fixes.
