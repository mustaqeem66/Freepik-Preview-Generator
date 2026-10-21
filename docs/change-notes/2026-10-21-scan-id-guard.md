# Scan-specific cancellation — 2026-10-21

## Confirmed defect
The privileged `cancel_scan()` bridge command cancelled whichever scan was active when it arrived. A delayed cancellation for scan A could therefore stop newly started scan B.

## Implementation
- `ScannerService.cancel_scan(scan_id)` checks the currently active scan ID under the existing scanner lock.
- `DesktopApi.cancel_scan(scan_id)` returns whether a cancellation signal was actually delivered.
- Optional ID preserves internal callers until the new frontend is merged.
- Add regression tests for incorrect IDs, matching IDs and absent scans.

## Limitations and rollout
This PR changes the backend contract but does not yet change the React caller. The next stacked PR must pass the explicit scan ID and handle cancellation confirmation.
A cancellation signal is not proof that a worker has exited. React must wait for `scan.finished`.
The desktop Windows hang root cause is unrelated and remains unconfirmed.

## Local validation required
- [ ] `python -m ruff check previewgen/api.py previewgen/scanner.py tests/unit/test_scan_cancellation_id.py`
- [ ] `python -m pytest tests/unit/test_scan_cancellation_id.py tests/unit/test_scan_race.py -q`
- [ ] Full suite and desktop scan/cancel/restart smoke after the frontend lands.
