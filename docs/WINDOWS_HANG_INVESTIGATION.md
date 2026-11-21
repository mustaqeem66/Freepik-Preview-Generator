# PreviewGen — Windows “Not Responding” investigation

**Date:** 2026-10-20, root cause established 2026-10-23. **Scope:** source audit of current `main`, screenshot of a faded idle/light-theme window with `PreviewGen (Not Responding)`. **Conclusion:** the hang is Windows' unresponsive-window effect on the WebView2 message pump, caused by pywebview recursively introspecting the bridge API into the .NET object graph — see the 2026-10-23 section below for the trace, the reproduction and the fix.

## Verified source findings

| Priority | Evidence | Change / decision |
| --- | --- | --- |
| High — diagnostic blind spot | `desktop_runtime.bridge_is_stalled()` requires outstanding backend work; idle hangs are invisible | Add a bounded Win32 `SendMessageTimeoutW(WM_NULL)` window probe on a separate daemon, requiring 3 failures before logging |
| Medium — avoid startup I/O delays | `entrypoint.main()` synchronously swept old temp directories before invoking the GUI. `cleanup_stale_temp_dirs` materialized every entry from shared temp storage | Schedule cleanup in a background daemon on desktop launches, scan with entry/time budgets |
| Medium — no in-app log access | User had to locate per-platform logs manually | Add a `Diagnostics` toolbar button that opens the existing local log directory via an authorized bridge call |
| Low — first-run friction | Empty preview offered no direct start action | Add a contextual `Choose Input Folder` button and actionable empty-state copy |
| Low — README guidance | README described marketing guarantees/unsupported claims and had no reliable UI-hang triage | Replace with installation matrix, exact limits/caveats, troubleshooting and reproducible test commands |

## 2026-10-23 — root cause identified from native Windows traces

The user's own packaged-app logs (`%LOCALAPPDATA%\PreviewGen\logs\previewgen.log*`, four rotated files, Windows 11 10.0.26200, `frozen=True`) contain the trace that was missing. **637 error lines in 17 storms**, every one of the form:

```
[ERROR] pywebview: Error while processing window.native.ActiveControl.DefaultFont.FontFamily.
         GenericSansSerif.GenericSansSerif.[...hundreds deep...]Families.SyncRoot.[...]:
         maximum recursion depth exceeded
[ERROR] pywebview: Error while processing window.native.ActiveControl.ZoomFactor:
         CoreWebView2Controller members can only be accessed from the UI thread.
         ---> System.InvalidCastException
            at System.StubHelpers.StubHelpers.GetCOMIPFromRCW(...)
            at Microsoft.Web.WebView2.Core.CoreWebView2Controller.get_ZoomFactor()
[ERROR] pywebview: Error occurred in script
```

**Mechanism.** `webview.util.get_functions()` (pywebview 6.2.1) recursively introspects `dir(js_api)` to build the page's bridge surface, skipping only names starting with `_` and objects marked `_serializable = False`. Before PR #74 the API object held the window in a **public** attribute (`self.window: Any | None = None`) and nothing was marked non-serializable, so the walk descended `window` → `Window.native` → the live WinForms `Form` → the WebView2 control graph:

- `FontFamily.GenericSansSerif` and `IList.SyncRoot` hand back a *fresh* instance per access, so pywebview's `id(obj)` memo never trips: the walk recurses until `RecursionError`, which it logs per name and then continues past.
- Every WinForms/WebView2 property it touches is a **cross-thread .NET/COM call issued from the bridge-injection thread while that thread holds the GIL**. WebView2 rejects them (`GetCOMIPFromRCW`), and the calls that do not reject must be marshalled onto the thread that owns the message pump.
- The pump needs the GIL in return — pywebview's own WinForms `timer_tick` runs a Python delegate every 500 ms, and every `evaluate_js` is a blocking `Control.Invoke` with an untimed `semaphore.acquire()`. That is a circular wait: the pump stops servicing `WM_PAINT`/input, and Windows labels the window `(Not Responding)`.

**Correlation in the traces.** Storms are bounded by page injection: the `Frontend mounted and reported ready` marker follows the last storm line within the same second, and ready latency equals storm duration — 24.5 s and 35.5 s in two sessions. In the session started `2026-10-20 23:49:52` the injection never finished at all: 58 storm lines run for 93 s with **no ready marker**, ending in `Initiating orderly lifecycle shutdown` at 23:51:54 — the reported symptom (faded idle window, user closes it) reproduced end to end.

**Reproduction without Windows.** `tests/unit/test_bridge_surface_exposure.py` replicates pywebview's walk (including its per-name `try`) against a stand-in object graph with the same pythonnet shape — a public attribute returning an object with self-renewing properties:

| API object shape | bridge names | nested toolkit paths | injected payload | walk cost |
| --- | --- | --- | --- | --- |
| public `window` (pre-#74) | 1271 | 1238 | 4.9 MB | 54 ms here; unbounded on a real .NET graph |
| private `_window` + `_serializable` guards (current) | 33 | 0 | 619 bytes | 0.10 ms |

A multi-megabyte `run_js` payload is also what produced `Error occurred in script`.

**Fix status.** PR #74 (merged 2026-10-22 11:49, *after* every logged storm) renamed the attribute to `_window` and marked every internal object `_serializable = False`, which removes the toolkit graph from the walk entirely; the two new tests pin the flat surface, forbid any dotted name, and bound the injected payload size. The original screenshot's cause is therefore identified and closed at the source level.

**Still open for this issue.** Acceptance still requires the installed and portable Windows idle and interaction matrix below. Residual amplifiers: `evaluate_js` has no timeout; the 500 ms `timer_tick` plus `Join(500)` main-loop keep two 2 Hz Python↔.NET handoffs on the pump; two `Lenis` `autoRaf` loops keep WebView2 compositing at 60 fps while the app looks idle; and the gallery/comparison 60 s pollers each force a full pump round trip and can serialize behind `render_sync`.

## 2026-10-20 audit — what could not be concluded then


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

**Current status:** Root cause is identified from the packaged Windows traces and reproduced by `tests/unit/test_bridge_surface_exposure.py`; PR #74 removes the .NET graph from the bridge walk. Remaining for issue #19 closure: run the packaged Windows idle health test (`scripts/windows_idle_health.py`, 300 s) on a build that contains #74, on installed and portable, at 100/125/150/200% DPI.

## November portable observation — not a passing idle test

Tested the portable EXE from [CI run 44778995430](https://github.com/mustaqeem66/Freepik-Preview-Generator/actions/runs/44778995430), commit `5215863460205aca1c4c61a0c4a315e0caec9bb0`, EXE SHA-256 `4fa5296aaf77802bd3cebc657bc76e4d61e34784eaac6ea03935cb460fce199e`. Windows 11 build 26200, WebView2 `157.0.4341.60`, window DPI 96 (100%).

The frontend reported ready. The 300-second monitor recorded 83 responsive, 0 unresponsive, then 18 no-window samples. The window disappeared about 250 seconds into the observation; the app logged orderly shutdown. The reason for closing was not established. The monitor correctly failed the 300-second acceptance check; this did not reproduce the original message-pump hang.

Local evidence: `local-native/windows-portable-5215863/idle.csv` and `app-lifecycle.log`. The installer and other DPI settings were not tested.

## November installed observation — the freeze reproduced, on a stale build

Tested the **installed** PreviewGen 2.1.2 at `%LOCALAPPDATA%\Programs\PreviewGen\PreviewGen.exe`, SHA-256 `a5492e5c61223357489994cb258b22231998346dcb6dcdc665a4f82bbdff440e`, Windows 11 build 26200, WebView2 `157.0.4341.60`, DPI 96 (100%). Authenticode: `NotSigned`.

The 300-second monitor recorded **1 responsive and 100 unresponsive** samples. The window was present and matched by title throughout; the process stayed at 11 threads with all threads waiting, and `CloseMainWindow` never completed. The monitor failed the acceptance check.

The application log explains why:

```
[ERROR] pywebview: Error while processing window.native.AccessibilityObject.Bounds.Empty.Empty.Empty...
[ERROR] pywebview: Error while processing window.native.DefaultImeMode.AlphaFull.AlphaFull.AlphaFull...
[ERROR] pywebview: Error while processing window.native.browser.webview.AllowExternalDrop:
    CoreWebView2Controller members can only be accessed from the UI thread.
```

That is the bridge injection storm: pywebview walked the live `window.native` .NET graph and injected it into the page. It is the same defect PR #74 fixed by renaming the attribute to `_window`.

**This installed build predates the fix.** The `v2.1.2` tag points at `2958525` (2026-10-20); the bridge fix is `de1b6e6` (2026-10-22). The installed EXE's own file timestamp is **2026-10-20 15:40**, two days before the fix. The frozen binary was therefore built from a commit before the fix, so this reproduction confirms the original defect and the fix's premise — it does **not** show that current `main` is still affected.

Evidence: `local-native/windows-installed-2.1.2/idle.csv` (SHA-256 `0b3869a56fb9f41309eb4a40d006c6be5079919d732a83a11a7a02f49dd2a641`) and `diagnostics.log`.

The remaining acceptance work is unchanged: run the same 300-second check against a build that contains `de1b6e6`, on installed and portable, at 100/125/150/200% DPI. Until that passes, issue #19 stays open.

## November CI candidate observation — the fix holds

Ran the same 300-second check against the portable EXE from [CI run 44778995430](https://github.com/mustaqeem66/Freepik-Preview-Generator/actions/runs/44778995430), commit `5215863460205aca1c4c61a0c4a315e0caec9bb0`, EXE SHA-256 `4fa5296aaf77802bd3cebc657bc76e4d61e34784eaac6ea03935cb460fce199e` — a build that **contains** the bridge fix `de1b6e6`.

Result: **99 responsive, 0 unresponsive**, and the monitor exited `0` (PASS). The last two samples report `no-window` because the app was closing after the observation window; the window was present and matched by title for the rest of the run. The candidate's own isolated log contains **no** `Error while processing` entries, unlike the stale installed build above.

Evidence: `local-native/windows-candidate-5215863/idle.csv` (SHA-256 `9f5b36c545c33032a703c7d58819354f2af645775565f2d0293a7925eac72458`).

So the bridge injection storm was the cause of the original freeze, and the fix removes it on Windows at 100% DPI. **Issue #19 still stays open**: the installed build, the installer/upgrade/uninstall path, and the 125/150/200% DPI matrix are not covered by this run.
