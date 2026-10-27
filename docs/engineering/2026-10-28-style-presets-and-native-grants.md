# Browser-local style presets — native grants stay authoritative

**Source branch:** `feat/grant-safe-style-presets-20261028`. A style preset provides named, locally reusable watermark/background/framing/camera/export-size settings (maximum eight presets, names 1–40 characters). The Studio Inspector exposes **Save style**, **Apply style**, and **Delete style**. Existing first-run defaults and state saving remain unchanged.

## Security contract

The preset format uses a hardcoded **allowlist** of aesthetic fields and the canonical frontend settings validator. It categorically excludes `logoPath`, `fontPath`, `inputFolder`, `outputFolder`, `sameFolder`, `overwritePolicy`, permissions, revision IDs, and unknown properties. A preset can never grant access to external files or set an unapproved export directory. The user must choose logo/fonts, folder and output destinations through existing native picker workflows.

Presets use bounded WebView `localStorage` with a schema version and an explicit 16KB limit. Storage can be disabled or corrupted; the UI reports write errors rather than claiming save success. Reads fail safely to an empty preset list and sanitize every style property on load. This is not cross-device sync, encrypted data storage, or a license to bypass native grants. Do not place customer secrets in preset names or watermark text.

## Local acceptance checks

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run build
cd ..
python scripts/check_release_locally.py --mode full
```

Manual native validation: create and apply several presets in light/dark theme; confirm the selected logo/font and native source/export grants cannot be changed or authorized by the preset, including after restart. Corrupt WebView localStorage intentionally and verify safe fallback; exercise full preset list and quota denial. Confirm preview and export update from the applied style using normal settings persistence. Cover Windows/Linux/macOS separately.

**Verification status:** tests authored, no repository-wide local CI or packaged native application executed by this PR author. All commits use `[skip ci]`; hosted Actions were not manually invoked.
