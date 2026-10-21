# Scan cancellation terminal UX and asset-source isolation — 2026-10-21

## Confirmed problems
- The UI declared cancellation as soon as the cancel bridge call returned, even if the worker had not yet stopped.
- Cancelling before start_scan returned its ID could abandon an active scanner.
- The previous folder's assets could remain visible under a newly selected folder.
- A delayed command for a superseded scan risked affecting a newer scan without ID scoping.

## Implementation
- Send an explicit scan ID on cancellation; defer until an in-flight start_scan response yields its ID.
- Wait for the scan.finished terminal event instead of assuming the worker stopped.
- Bound unknown cancellation state to 30 seconds and surface a recoverable error instead of hanging forever.
- Clear assets when the folder changes; preserve previous results on same-folder rescans, while disabling preview and export.
- Keep terminal events and progress restricted to their own scan IDs.
- Add tests for pending-start cancellation, old asset isolation and confirmed cancellation.

## Dependency and remaining verification
This is a stacked PR based on #25 (backend scan-ID guard), not yet mergeable directly to main.
- [ ] npm ci, npm run typecheck, npm test, npm run build
- [ ] Native Windows WebView2 cancel/start/restart and empty-folder tests.
- [ ] Cross-platform UI tests and slow/network folder checks.
- [ ] Confirm the Windows idle-freeze root cause separately; this change does not claim that fix.
