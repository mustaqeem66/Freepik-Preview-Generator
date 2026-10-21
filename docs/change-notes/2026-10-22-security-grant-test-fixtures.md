# 2026-10-22 — Follow-up: legacy preview test fixtures must simulate grants

Issue #59 introduced a real separation between exact file grants, native input-folder grants and output/log folders. Older tests for export-size calculation, the loopback preview server and rapid preview/probe responsiveness called the privileged `DesktopApi` with a raw source file path, relying on earlier implicit access.

These tests now grant their **known test fixture folders** explicitly with `DesktopApi.add_authorized_input_folder`, modeling a user having chosen those directories through the native picker. Production code remains unchanged. The unauthenticated, symlink-escape, ZIP-traversal and unauthorized-scan tests in `test_source_read_authorization.py` continue to prove ungranted source paths are denied.

Changed tests: `tests/unit/test_export_sizing.py`, `tests/unit/test_preview_server.py`, `tests/unit/test_interactive_hang_remediation.py`. The responsiveness timing expectations and actual rendering behavior are unchanged.

Local execution:
```bash
python -m pytest tests/unit/test_export_sizing.py tests/unit/test_preview_server.py tests/unit/test_interactive_hang_remediation.py tests/unit/test_source_read_authorization.py -q
python scripts/check_release_locally.py --mode full
```

Tests are source-updated but not executed in this authoring environment; no GitHub Actions run is requested. Commit uses `[skip ci]`.
