# 2026-10-22 — Source authorization boundary (#59)

## Security problem and decision

Public React bridge operations previously validated only that an arbitrary supplied path existed before rendering, probing or reading dimensions. More importantly, a bridge caller could invoke `start_scan` with an arbitrary folder, causing the API to authorize the same path, and `save_settings` could persist a new `inputFolder` for subsequent restoration. Merely protecting the renderer methods would leave those escalation routes open.

The API now distinguishes **source-read grants** from the existing broad helper paths used to open reports/logs and from explicitly chosen output roots. Only a native input folder picker (or a previously trusted saved input root) grants a source directory; the Add Files native picker grants exact files. ZIP member reads require the containing ZIP archive under an input grant, a safe relative archive entry and an allowed asset extension.

## Changes and rationale

- Central `DesktopApi._source_read_error` validates ordinary source paths and `zip://` archive entry URIs, checks extensions, canonicalizes filesystem paths, and rejects ungranted reads. The method runs *before* spawning preview, probe, synchronous fallback, dimension or single-export work.
- All public preview/probe/dimension/export methods now enforce the same source authorization, including the thumbnail gallery and comparison view.
- `start_scan` and synchronous `scan_folder` no longer self-authorize caller-provided paths. The UI's editable path field is now read-only and tells users to select input folders with **Choose Folder**. Rejected scans show a useful selection-required message.
- `save_settings` refuses to persist an arbitrary `inputFolder`, preventing the persistence-to-restore grant escalation. Previously saved legitimate input folders continue to restore through local app preferences.
- User-selected logos and fonts gain exact independent read grants; arbitrary paths in renderer config and settings are rejected even if a normal source file is authorized. On restore, explicitly persisted local logo/font selections retain their grants.
- Current output-folder picker and batch destination authorization are unchanged. Existing unit tests were updated to explicitly simulate user grants rather than relying on arbitrary path strings.
- Unit tests cover unauthorized vs. approved source, output/read separation, selected-file revocation, directory symlink escape, ZIP archive and traversal, scan self-authorization denial and logo/font path controls.

## Security scope and limitations

This is an application-level capability check on the privileged bridge, not a filesystem sandbox for native dependencies. A user or malware with direct OS access can still read local files through the operating system. Previously granted directories intentionally expose their contained supported artwork. Long-running work already submitted before file-grant revocation may finish (revocation applies to *new* requests). Native picker selection and settings restored from disk remain trust decisions. Archive extraction must still enforce bounded member sizes and traversal checks in its isolated worker.

## Validation requirements

```bash
python -m pytest tests/unit/test_source_read_authorization.py -q
python -m pytest tests/unit/test_scan_race.py tests/unit/test_scan_page_bridge.py tests/unit/test_legacy_scan_bridge_compat.py -q
python scripts/check_release_locally.py --mode full
```

Test Windows, macOS and Linux packaged WebViews with real file and folder dialogs; verify a user can choose a folder, reopen previously selected folders, select individual files and custom branding, then preview/probe/export normally. Test unauthorized JS path injection and CSP in native WebView (#20). Do not close #59 or claim a secure release until full local/native verification is complete.

**Status:** Source implementation and regression tests committed, not executed in native target OS environments. Commits use `[skip ci]` to avoid hosted GitHub Actions.
