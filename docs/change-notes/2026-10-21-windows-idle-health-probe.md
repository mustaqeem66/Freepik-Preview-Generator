# Windows packaged-app idle health probe — 2026-10-21

## Purpose
The long-standing PreviewGen `Not Responding` report has **no verified root cause**. Short source-mode GUI startup handshakes cannot establish that a packaged installation remains responsive for minutes. This manual, no-extra-dependency Win32 probe collects bounded, PID-targeted message-pump health observations.

## How to run (PowerShell on Windows)
1. Build or install the latest PreviewGen EXE. Open the app and leave it idle (not running `--gui-smoke-test`).
2. Locate the process that actually owns the visible window (one-file packaged builds can spawn child processes):
   ```powershell
   Get-Process | Where-Object { $_.ProcessName -match 'PreviewGen' } |
     Select-Object Id, ProcessName, MainWindowTitle
   ```
3. Start the monitor using the ID of the process with a PreviewGen window:
   ```powershell
   python scripts/windows_idle_health.py --pid 12345 --seconds 300 --interval 3 --csv .\previewgen-idle-health.csv
   ```
4. Repeat for an installed setup build and the portable executable, idle and after opening a native chooser. Keep the app running until the probe completes.
5. Inspect `%LOCALAPPDATA%\PreviewGen\logs\previewgen.log` locally. If the probe reports **FAIL**, correlate timestamps with `HANG DIAGNOSTIC` messages and Windows Event Viewer → Application.

## What it does and does not verify
- Uses Win32 `EnumWindows` and bounded `SendMessageTimeoutW(WM_NULL)` against the visible PreviewGen top-level window of the specific PID.
- Requires three consecutive unresponsive or missing-window samples by default to fail.
- Exports only timestamps, PID, response categories and window counts. Does not record screen pixels, filenames, artwork, native dumps or private log contents, and does not upload anything.
- Does not kill, restart, inject, or manipulate the running app.
- A failed probe can also reflect a modal system dialog, process exit, or machine overload. A passing run only verifies *the observed interval*.
- **Root cause remains unknown** until correlated diagnostics or a reproducible Windows trace identifies the stalled code path.

## Validation required
- [ ] `python -m pytest tests/unit/test_windows_idle_health.py -q`
- [ ] `python -m ruff check scripts/windows_idle_health.py tests/unit/test_windows_idle_health.py`
- [ ] Test with real Windows 10 and Windows 11, at 100% and 200% DPI, and installed + portable packages.
- [ ] Confirm the no-window threshold triggers if the monitored process exits.
- [ ] Record OS build, GPU/driver and WebView2 Runtime version privately with the resulting timestamps.
- [ ] Do not claim the screenshot's original hang is fixed based on a diagnostic gate alone.

See `docs/WINDOWS_HANG_INVESTIGATION.md` and GitHub issue #19 for the authoritative root-cause investigation.
