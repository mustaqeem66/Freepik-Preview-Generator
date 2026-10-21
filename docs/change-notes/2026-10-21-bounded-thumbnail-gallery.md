# PreviewGen Studio — bounded thumbnail gallery (2026-10-21)

## Product and engineering decision
Creative desktop references in `docs/design/2026-10-21-macos-premium-ux-research.md` argue for quiet, artwork-first browsing. List view remains the default and the existing virtualized library search/selection stays intact. A Gallery toggle presents two columns within PreviewGen's 200–360px resizable library, with image tiles and format/name labels.

## How images are generated
- Gallery asks the backend for **only visible cells**, using a 120ms wheel/scroll debounce and 16-path maximum. Rendered React tiles are virtualized by row and stay bounded with 100k+ assets.
- The backend's `ThumbnailCoordinator` has one background render thread and a 20-image session LRU. It reuses `PreviewCoordinator.render_sync`, which renders in an isolated worker process with a six-second per-thumbnail timeout and memory cap. It does not block the JS bridge or steal the live interactive preview's worker slot.
- Neutral thumbnails are capped at 192px and independent of live inspector styling. They are **navigation aids**, not exact color/overlay previews or exported files. Use the center canvas for the authoritative preview.
- JPEGs reuse the existing private 127.0.0.1 preview server. The coordinator retains thumbnails so normal current/previous preview pruning does not break the gallery, evicts old URLs with explicit release, and closes before the preview server shuts down.
- Requests for unsupported, missing, unauthorized or too many paths are rejected. Folder scans and Add Files grants are validated; a file path from an arbitrary web/JS caller is not an authorization source. ZIP members are accepted only through the scan-produced zip:// URI format under authorized source roots.
- Stale render events are ignored on both sides when the visible set changes; failed tiles display a neutral placeholder without infinitely retrying. Gallery never decodes or renders thousands of images in the browser.

## UI/accessibility
- Search query persists when toggling List/Gallery; each tile preserves the original source index, even after filtering.
- Gallery role=listbox with aria-activedescendant, selected option, group keyboard arrows in two columns, Home/End and Page navigation. The active tile remains in the DOM during out-of-window selection jumps.
- Only a small set of 192px thumbnails are ever loaded in the DOM; when the bridge is unavailable, format placeholders work without falsifying imagery.
- No third-party UI components, no external image hosts, no CSS imitation of macOS titlebar controls, and no new runtime dependency.

## Compatibility and risks
1. The cache is session-scoped and the preview server also has an age-based eviction policy; a gallery left open for a very long time may show a missing image until the visible set is re-requested. Re-evaluate server/cache expiry consistency before declaring long-idle native QA complete.
2. The sync isolated renderer may spend up to six seconds on an expensive unsupported format; only one gallery render is in flight but native Windows idle responsiveness must still be checked.
3. Existing Add Files implementation (#34, including merged-in #35) is the **base branch**. This PR must be rebased/retargeted after #34 merges; no independent release until combined workflow tests.
4. Native Cocoa/WebView2/WebKit differences, path permissions and CSS rendering need platform verification.

## Acceptance gates
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] `python -m ruff check previewgen/thumbnail_coordinator.py previewgen/api.py tests/unit/test_thumbnail_coordinator.py tests/unit/test_thumbnail_api.py`
- [ ] `python -m pytest tests/unit/test_thumbnail_coordinator.py tests/unit/test_thumbnail_api.py tests/unit/test_native_add_files.py -q`
- [ ] Native Windows 10/11 and macOS, 200px pane, source folder + ZIP members + direct file selection + corrupted assets + high DPI + keyboard/VoiceOver.
- [ ] 100k asset library scroll and sustained five-minute idle. Confirm bounded worker count and cache retention with private logs. Run Windows idle probe for release blocker #19.
- [ ] Verify thumb URLs still load across repeated long scroll, and freeing the gallery does not delete current live preview.

**Status:** Draft source implementation, not compile/test/native QA verified. All commits use `[skip ci]` and run no GitHub Actions.
