# Bounded scan-result transfers for the desktop bridge

**Date:** 2026-10-21  
**Priority:** P0-risk mitigation and Windows diagnostic work, not a confirmed freeze fix  
**Branch:** `perf/paged-scan-webview-20261021`

## Audit evidence

`ScannerService._execute_scan` can return up to approximately 5,000 asset descriptors, each including source paths and ZIP member details. Previously, `DesktopApi._on_scan_finished` passed the full list to `_dispatch_envelope`, which invoked one synchronous `window.evaluate_js(...)` with the entire JSON payload. That operation runs from the scan completion callback and can send a large JavaScript string across a native desktop WebView message boundary.

A large synchronous injected result is a **possible responsiveness stressor** in WebView2, not a proven explanation for issue #19. We do not claim to have reproduced the original Windows `Not Responding` hang or eliminated it.

## Design and decision

- **Legacy path remains:** small results (up to 128 entries and at most 32 KiB of file-list JSON) retain the existing `scan.finished` envelope. This preserves old UI tests and tiny-folder behavior.
- **Large result:** the same terminal event contains scan status, truncation, `total`, errors and `paged: { total, pageSize: 128 }`, but **no asset rows**.
- **Pull pages:** `DesktopApi.get_scan_page(scanId, offset, limit)` serves sequential read-once pages. Each page is capped to 128 rows **and** a conservative 32-KiB serialized metadata budget, with 512 bytes reserved for the wrapper. No extra filesystem reads or new path permissions are introduced.
- **Session memory bounded:** only one completed scan's result can be retained for paging. New scans, completed consumption and shutdown revoke it. The scanner itself already caps discovery; no source artwork bytes, thumbnails or remote requests are transferred.
- **Safety and cancellation:** frontend compares scan ID, offset, total, positive progress, row schema and next offset. It **only replaces the current library once every page has validated**. New folder scans or cancelling the page transfer invalidate pending results. One bridge page request has an 8-second deadline and surfaces an actionable error on failure.
- **Race mitigation:** early `scan.finished` events (arriving before `start_scan` resolves) are buffered under their scan ID. Superseded Python scan completions cannot clear a later scan's page cache.

No extra runtime dependencies, WebView privileges, new browser origins, or asynchronous promises from the Python bridge are required. This does not alter the batch generator's filesystem traversal.

## Tests added

`tests/unit/test_scan_page_bridge.py` checks 5,000 long-path records without a huge terminal event, serialized page limits, source ordering, strict sequential offsets, read-once result release, stale ID rejection, small-scan backward compatibility and single-record byte overflow.

`frontend/src/scannerPages.test.ts` checks 321 assets, stale requests, invalid offsets and totals, and missing backend support. Four `useScanner` regression cases exercise all-or-nothing page adoption, rapid folder changes, page failure and early terminal delivery.

## Local QA (requires a current checkout and supported environment)

```powershell
python -m ruff check previewgen/api.py tests/unit/test_scan_page_bridge.py
python -m pytest tests/unit/test_scan_page_bridge.py tests/unit/test_event_envelope.py tests/unit/test_scan_race.py tests/unit/test_scan_cancellation_id.py -q
cd frontend
npm ci
npm run typecheck
npm test
npm run build
cd ..
python scripts/check_release_locally.py --mode full
```

For actual Windows evidence, build the **current branch**, open a packaged GUI with a 5,000-asset test folder, and run (with the PID owning PreviewGen's actual visible window):

```powershell
python scripts/windows_idle_health.py --pid <PID> --seconds 300 --interval 3 --csv .\previewgen-idle-health.csv
```

Observe launch, tiny and large folders, a ZIP with permitted members, slow/network directories, rapid re-scan/cancel, output generation, idle, native dialogs and exit. Repeat installed versus portable, Windows 10/11, 100/125/150/200% DPI. Inspect `HANG DIAGNOSTIC` locally, comparing **actual GUI responsiveness** with the previous build. A success here is evidence only for the observed runs.

## Known boundaries

- `get_scan_page` is one sequential cursor per latest scan. Failed requests require a fresh scan, by design; no random seek or arbitrarily persistent cached file handles.
- The scanner may transiently include one additional ZIP entry at its quota boundary. The frontend's defensive upper limit allows 5,001 descriptors, while the original scanner quota is nominally 5,000.
- 8-second per-page timeout avoids indefinite UI state. This does **not** interrupt an OS-level slow bridge call; the generation check prevents a late response being applied after supersession.
- Existing Windows issue #19, production CSP native validation #20 and release packaging issue #22 are **still open**.

**Status:** Source changes and regression cases committed, but no local Python/TS suite or native Windows/WebView2 run was executed in this authoring environment. Commits use `[skip ci]`; GitHub-hosted Actions minutes should remain unused.
