# Cross-platform native window chrome controls (2026-10-21)

User request: Windows/Linux desktop windows should display Minimize and Fullscreen controls at the **top left**, with Close at the **top right**. For macOS place all three controls at the **top right**, as specifically requested (rather than pretending to copy macOS's usual top-left traffic lights).

Implementation: pywebview uses a frameless native window and a dedicated `DesktopTitlebar` component. Actions are delegated only to `Window.minimize()`, `Window.toggle_fullscreen()` and `Window.destroy()` through `DesktopApi.window_action`. No arbitrary method name can be invoked. The title is a `pywebview-drag-region`; buttons live outside drag regions so click interaction works. Close is queued briefly so the JS bridge can reply before its WebView disappears. Screen reader labels and keyboard focus are provided.

**Safe fallback**: set `PREVIEWGEN_NATIVE_TITLEBAR=1` in the app's environment before launch to use standard system-managed window decorations and hide the custom controls. This is important for unusual Linux/Wayland window managers, native accessibility, resizing, task switchers, fullscreen state, Windows snap zones and macOS window management. Custom frameless behavior cannot be certified from CSS unit tests alone.

Recommended acceptance:
- Windows 10/11 WebView2 installed + portable: close/minimize, restore from taskbar, maximize/fullscreen toggle, alt-F4, Win+arrow, DPI 100/125/150/200%, resize to 1100x700.
- Linux GTK + Qt if shipped: native move/resize in X11 and Wayland, focus, minimize/restore, Close, keyboard, file dialog remains attached to the parent, fallback.
- macOS Cocoa: top-right controls, native close, restore/fullscreen transition, VoiceOver, Stage Manager and full screen.
- Verify that absence of pywebview (Vite dev mode) does not fake OS actions and that the native-fallback option retains the OS chrome.

Source/typed bridge/unit tests committed, **native interaction and packaged smoke not yet performed**. Keep draft until platform validation. Commits include `[skip ci]` due to Actions minute budget.