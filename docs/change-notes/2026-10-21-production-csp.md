# PreviewGen packaged WebView CSP — 2026-10-21

## Goal and threat model
The desktop window runs a privileged Python bridge. In-page script injection could invoke bridge methods. CSP is an additional defense-in-depth layer to stop *externally loaded scripts*, media, frames, objects and unsolicited network requests; it is **not** a sandbox and does **not** replace bridge path authorization or XSS prevention.

## Code change
- Vite injects a policy into production `dist/index.html` **before application scripts**; development HMR is intentionally unchanged.
- `script-src 'self' 'unsafe-eval'` permits the local bundled app and accommodates pywebview JavaScript evaluation. No `'unsafe-inline'` script permission.
- `style-src 'self' 'unsafe-inline'` is currently necessary because the React canvas/list/layout use inline style properties.
- `img-src` permits session-token-protected JPEG previews from `http://127.0.0.1:<ephemeral-port>`; no remote image hosts.
- `connect-src` permits loopback transports for native WebView variations while denying public remote hosts.
- Disable objects, frames, workers, media and form submissions in this app-specific policy.
- Add Vitest and built-artifact checks so release builds cannot silently omit the policy.

## Limitations and compatibility blockers
1. CSP delivered through `<meta>` supports fetch directives but **not** the `frame-ancestors` directive. It must not be advertised as clickjacking protection.
2. `'unsafe-eval'` weakens script execution containment but is used for pywebview's eval-based bridge helpers; native compatibility and eventual replacement with `run_js` require separate investigation.
3. Loopback ports are not fixed; an XSS script already running in the trusted window could still reach other allowed loopback services. Keep bridge authorization independent of CSP.
4. WebView's file URL handling and pywebview script-injection behavior are platform-specific. Static tests cannot verify bridge readiness.
5. Production-only policy means local dev mode is **not** protected in the same way.

## Mandatory acceptance before merging
- [ ] `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
- [ ] `PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE=1 python -m pytest tests/frontend/test_bundle.py -q`
- [ ] Windows WebView2 packaged app: `frontend_ready`, folder picker, scan, preview image, export, settings persistence, 3D interaction, devtools security warnings.
- [ ] macOS Cocoa and Linux GTK/Qt: same operations, especially pywebview bridge initialization and loopback access.
- [ ] Verify external scripts/images/frames are blocked without breaking same-origin bundled assets.
- [ ] Check default CSP + native lifecycle handling at 100/125/150/200% DPI and idle session.
- [ ] Verify an actual Windows installer and portable zip, macOS DMG and Linux AppImage.

**Status:** Source implementation proposed in a draft PR. Not validated in native packaged WebViews; issue #20 stays open.
