# Batch destination authorization hardening — 2026-10-21

## Root cause
`DesktopApi.start_batch` automatically authorized the destination path supplied by the JavaScript caller, which let the request itself grant write capability.

## Change
- Require batch destinations to be authorized before launching the worker or creating any directory.
- Preserve saved directory sessions by authorizing existing paths retrieved from validated on-disk settings at initial UI handshake.
- Provide an actionable error directing users to the native output-folder picker.
- Add positive and negative authorization regression tests.

## Scope and remaining risks
This is a targeted batch-destination fix, **not a complete filesystem sandbox**. Source scanning still accepts typed paths, and local settings are treated as user-trusted. Follow-up authorization policy work must separately address source file read capabilities, symlinks and native multi-file import.

## Release validation
- [ ] `python -m pytest tests/unit/test_batch_api_regressions.py -q`
- [ ] Full `python -m pytest tests/ -q` and Ruff.
- [ ] Source browse / output browse / same-folder / restart / invalid-destination GUI checks.
- [ ] Verify Windows installed and portable builds.
Tests and native GUI checks were not run during this remote review.
