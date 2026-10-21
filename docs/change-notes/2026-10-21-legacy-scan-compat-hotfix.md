# Scan-result protocol compatibility hotfix — 2026-10-21

## Reason for the immediate PR
PR #41 introduced paged scan terminal envelopes in the backend before the corresponding React consumer was merged. Old frontend bundles that use `start_scan(folder)` cannot read `paged` metadata and would show an empty library after a successful scan of more than 128 assets. This is a real protocol-compatibility regression risk independent of the unresolved Windows idle hang.

## Correction
The backend defaults to the original complete `scan.finished` payload unless the caller explicitly uses `start_scan(folder, paged=True)`. The enhanced frontend in PR #42 will opt in only when its page-fetch API is available. A backend update alone therefore cannot silently require a new frontend.

This is **compatibility containment**, not a proven Windows hang fix. The legacy oversized event can still stress the WebView until an updated frontend ships, so full paging integration and native stress tests remain necessary.

## Verification
- `python -m pytest tests/unit/test_legacy_scan_bridge_compat.py tests/unit/test_event_envelope.py -q`
- `python -m ruff check previewgen/api.py tests/unit/test_legacy_scan_bridge_compat.py`
- Real packaged Windows test with older frontend/updated backend, folders of 10 and 500 assets.
- Then merge/test PR #42 and verify opt-in paged behavior with 5,000 files.

No GitHub Actions are needed; use local checks. Test code committed, **not executed here**.
