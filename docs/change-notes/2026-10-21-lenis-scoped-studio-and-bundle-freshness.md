# Scoped Lenis motion, stale frontend bundle prevention (2026-10-21)

## Why the user's screenshots still show old buttons and sliders
The GitHub `main` source already removed the visible **Commands** and **Diagnostics** toolbar controls in PR #46. It also placed `CanvasExportDock` inside the center preview pane, plus `studioControls.css` for light/dark slider dials. The screenshots show the old toolbar, default blue range controls and an outer full-width footer—strong evidence the *running desktop app* is serving an older generated frontend bundle or an old packaged executable. A git merge does **not** hot-reload a pywebview production window.

`previewgen.resources.get_html_dist()` in source mode previously checked `previewgen/frontend/dist` before the repository's **canonical** `frontend/dist`. A stale copied distribution could therefore take priority even after `npm run build`. Now development/source mode prefers the canonical Vite output. Frozen releases still use the resources embedded into that exact binary, not a nearby checkout.

### Practical recovery steps
Close the desktop application completely. In the *same git checkout* used to launch it:

```powershell
git checkout main
git pull --ff-only
cd frontend
npm ci
npm run typecheck
npm test
npm run build
cd ..
python -m pytest tests/unit/test_frontend_resource_preference.py -q
python -c "from previewgen.resources import get_html_dist; print(get_html_dist())"
```

After merging this PR, the last command in a **source** checkout should print `<repo>/frontend/dist/index.html` (not `<repo>/previewgen/frontend/dist/index.html`). Relaunch from source. If running a **PyInstaller installed/portable executable**, rebuild and reinstall **that executable** from your new sources and compiled UI: updating a git checkout alone cannot change the already embedded web files.

To verify the loaded UI, the header must have **no visible Commands or Diagnostics buttons**, the export dock must be inside the **center preview pane** (not under the whole three-pane workspace) and the sliders must show **charcoal/ivory concentric knobs rather than blue native dots**. A stale screenshot should be diagnosed as an asset/build mismatch before further UI edits.

## Lenis research and scoped design
Official docs: https://github.com/darkroomengineering/lenis and https://lenis.dev/ . Pin `lenis@1.3.27` rather than loading an external CDN at desktop runtime. The desktop production CSP and offline-by-default guarantees are preserved.

- One Lenis instance is attached to each outer **Library** and **Inspector** pane with `wrapper` and `content`. **No root/window Lenis instance.** Both panes retain their own scrollbars, content, keyboard behavior and independent scroll bounds.
- Wheel input uses `autoRaf: true`, bounded `lerp: 0.16` and moderate wheel multiplier. Native touch remains native (`syncTouch: false`). The canvas, native dialogs, text inputs, sliders and virtualized 100k-asset list/gallery bypass smooth-wheel interception.
- Reduce Motion disables Lenis entirely and dynamically destroys/recreates it if preference changes. React unmount/StrictMode cleanup destroys the instance and handlers.
- Other motion polish is deliberately quiet: short hover transitions on toolbar/dock/view toggles, no canvas pixel movement/parallax, visible keyboard focus, and no animation in high-contrast or reduced-motion mode.
- No framer-motion/GSAP dependency: Lenis is the only added runtime package. `npm ci` installs dependencies from `frontend/package-lock.json`; test a fresh cache before shipping. The npm lock currently pins the official 1.3.27 tarball URL and version; integrity metadata should be verified/refreshed by `npm install --package-lock-only` in a networked local checkout before release because this authoring environment cannot reach the npm registry.

## Test gates
1. `cd frontend && npm ci && npm run typecheck && npm test && npm run build`
2. `python -m pytest tests/unit/test_frontend_resource_preference.py -q`
3. `python scripts/check_release_locally.py --mode full`
4. Native smoke: Library outer scroll vs inner virtualized asset list; Inspector long-form scroll vs draggable sliders; no jitter during live preview; window resizes and Focus Canvas; Windows WebView2/Linux GTK/macOS Cocoa.
5. Verify dark/light, no assets/1000+ assets, keyboard navigation, reduced motion, screen reader, and 100/125/150/200% scaling. Check CPU after idle and that unmount/reopened panes do not leak animation loops.

**Status:** PR is a source-level implementation and tests, not proof of passing local/frontend/native gates. Commit messages use `[skip ci]` to preserve GitHub Actions minutes.
