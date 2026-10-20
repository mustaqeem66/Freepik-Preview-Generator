# PreviewGen — Windows “Not Responding” investigation

**Date:** 2026-10-20. **Scope:** source audit of current `main`, screenshot of a faded idle/light-theme window with `PreviewGen (Not Responding)`. **Conclusion:** the screenshot establishes a Windows UI message-pump hang, but it does not establish whether the underlying cause is WebView2, Python, native dialogs, a slow filesystem, or a driver.

## Verified source findings

| Priority | Evidence | Change / decision |
| --- | --- | --- |
| High — diagnostic blind spot | `desktop_runtime.bridge_is_stalled()` requires outstanding backend work; idle hangs are invisible | Add a bounded Win32 `SendMessageTimeoutW(WM_NULL)` window probe on a separate daemon, requiring 3 failures before logging |
| Medium — avoid startup I/O delays | `entrypoint.main()` synchronously swept old temp directories before invoking the GUI. `cleanup_stale_temp_dirs` materialized every entry from shared temp storage | Schedule cleanup in a background daemon on desktop launches, scan with entry/time budgets |
| Medium — no in-app log access | User had to locate per-platform logs manually | Add a `Diagnostics` toolbar button that opens the existing local log directory via an authorized bridge call |
| Low — first-run friction | Empty preview offered no direct start action | Add a contextual `Choose Input Folder` button and actionable empty-state copy |
| Low — README guidance | README described marketing guarantees/unsupported claims and had no reliable UI-hang triage | Replace with installation matrix, exact limits/caveats, troubleshooting and reproducible test commands |

## No root cause claimed yet

A UI responsiveness timeout is not proof of a Python deadlock. The Windows probe is diagnostic-only; it never calls `os._exit`, destroys the window or restarts pywebview. The existing watchdog's bridge silence is insufficient to conclude that a window is hung. The new detector logs all Python thread stacks if Windows fails three consecutive bounded message-probe attempts. Python thread stacks may not show the underlying native WebView2 or GPU call stack.

### Required Windows reproduction

1. Build **from this PR**, or test the next released version once published; the current v2.1.1 installer does not contain this watchdog.
2. Launch on a clean Windows 10/11 machine with Microsoft Edge WebView2 Runtime. Record the app version, Windows build, GPU/driver, WebView2 version, DPI scaling and whether the app is installed or portable.
3. Test idle launch (nothing selected) for 5 minutes, then small PNG source, 1000+ assets, ZIP, native folder dialog, light/dark theme switching, batch start/cancel/restart and exit. Repeat with and without Windows notifications.
4. When Windows displays `Not Responding`, wait at least 15 seconds for watchdog samples. Read `%LOCALAPPDATA%\PreviewGen\logs\previewgen.log` and search `HANG DIAGNOSTIC`.
5. Compare Python thread stacks with Windows Event Viewer → Application. If necessary capture a private memory dump for native wait-chain analysis (may contain artwork/private data).
6. File the smallest reproducible case, the last 30 **redacted** log lines and the exact scenario. Only after reproduction should a native WebView2 or renderer fix be stated as a confirmed root cause.

### Release acceptance checks

- Python `ruff`, `pytest`, frontend typecheck/Vitest/Vite build; no startup or cancellation regressions.
- Headless CLI smoke does **not** replace a real Windows `--gui-smoke-test` and a manual long-running idle test.
- Verify an installer wizard and portable ZIP separately; test a new install, changed location, desktop shortcut and uninstall.
- Inspect Windows 100/125/150/200% DPI, a smaller display, and reduced-motion/high-contrast accessibility.
- The screen-wide pale overlay in the screenshot is Windows' **unresponsive-window effect**, not PreviewGen's chosen color palette. Cosmetic changes do not cure its cause.

## Further audit backlog (not claimed fixed)

- Measure any synchronous `window.evaluate_js` dispatch and large scan-result payloads under 5000-assets stress tests; consider a bounded event queue if profiling shows it blocks producer threads.
- Test native dialogs on Windows (including slow/network folders) and verify no nested event-loop deadlocks.
- Add a Windows idle-UI health gate that uses the real signed packaged EXE, not a mocked or headless bridge.
- Review renderer/cancellation stress tests for abnormal WebView2/GPU memory growth and child process leaks.
- Make the inspector resizable, add searchable asset thumbnails, and implement true multi-file import end-to-end before advertising it.
- Add optional copy-redacted-diagnostics support only with explicit user review/consent. Never upload crash data or artwork automatically.

**Current status:** Source-level hardening and diagnostics are committed to this branch. No Windows native reproduction trace was supplied, so the original screenshot's exact root cause remains unconfirmed.
