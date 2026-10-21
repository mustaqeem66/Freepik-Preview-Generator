# Export destination permissions: separate from browse/log settings capabilities

## Issue detected in bridge audit
The source-read boundary was tightened in PR #61. However, single-file export and folder-mode batch used `is_authorized_path(output)`, a **general browsing authorization** which also includes the app's diagnostics and settings directories. Those system folders should never become write destinations simply because users are allowed to open them.

## Fix
`DesktopApi.is_authorized_export_destination` now authorizes a destination **only** when:
- the native output chooser or saved output preference explicitly granted that destination; or
- the destination is within a native-authorized *scanned input folder* and the workflow is the existing folder-mode **Same as input** operation.

An individual exact-file grant does not authorize the file's parent directory for output writes, even if that parent was scanned separately. An explicit output picker grant is required for Add Files.

The batch and single-export routes apply this helper before any output directory creation or renderer dispatch. Existing output grants are unchanged; broad log/config/browse permissions cannot silently be promoted to output capabilities.

## Tests
Regression cases simulate a diagnostic folder which has only general authorization, assert **no render or batch submission**, then grant output explicitly. Other cases protect exact-selected files and confirm Same-as-input remains valid.

Run:
```powershell
python -m pytest tests/unit/test_export_write_grants.py tests/unit/test_batch_api_regressions.py tests/unit/test_native_add_files.py -q
python -m ruff check previewgen/api.py tests/unit/test_export_write_grants.py
python scripts/check_release_locally.py --mode full
```

## Release evidence
This is a source authorization hardening change. It does not prove the pywebview CSP, renderer fidelity, Windows idle freeze, or signed installer safety. Require actual Windows/macOS/Linux packaged negative-path smoke tests. No hosted Actions minutes used; all commits use `[skip ci]`.
