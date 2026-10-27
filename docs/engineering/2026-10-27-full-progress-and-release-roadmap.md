# PreviewGen Studio — verified source progress and unfinished release work

**Audit date:** 27 October 2026  
**Repository:** `mustaqeem66/Freepik-Preview-Generator`  
**Branch:** `main` at `0bb941fda6f85d982b3fcea5a4d1bd4a6806118e` (read-only baseline; refresh before release).

## 1. Scope, provenance and honesty

This report reconciles the owner's expanded audit (`Pasted markdown(1).md`) with live repository files, the fixture inventory and GitHub PR/issue status on this baseline. No Windows, Linux or macOS native application run was conducted by the report author. A source fix, a fixture smoke test, and signed release approval are **three different results**.

## 2. Confirmed engineering progress

- Nine previously identified source discrepancies have code fixes. PRs **#95, #96, #97, #98 and #99 are merged into `main`**. See [the focused nine-issue ledger](2026-10-27-re-audit-remediation-ledger.md). The earlier ledger incorrectly called PR #97 a draft after it merged; this newer document supersedes that status.
- Renderer processes have timeouts, cancellation and resource caps, including bounded archive-member extraction, and preview transport uses a localhost session-guarded server. These mechanisms are defenses, not proof of complete containment.
- Source-read and export-write grants exist for native picker paths; secure deployment still needs adversarial packaged-WebView QA (issue #59).
- `previewgen/renderers/capabilities.py` declares **47 extensions**, including the `.zip` container, i.e. **46 direct preview extensions**. The current `renderer-samples.json` contains **12 files covering 11 distinct suffixes**; `sample_pbr.glb` exercises another GLB case rather than a new extension.
- Independent source-app/version references are supported by `scripts/audit_renderer_matrix.py`, but real licensed third-party oracle assets and native release proof are outstanding (issue #60).
- Built-in watermark presets (object-centered and corners), `modelColor` preview rerendering, creator archive hardening, Maya prefix bounds, mixed-node color normalization, and stable ZIP mesh-cache identity are source-merged. Fully textured UV shading is **not** implied.

## 3. Active acceptance issues — do not close on source changes alone

| Issue | Work remaining | Release evidence |
|---|---|---|
| [#19](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/19) | Isolate and verify Windows native idle-hang root cause | Installed and portable WebView2 trace, 5-minute idle / picker / scan / cancel tests at multiple DPIs |
| [#20](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/20) | Production CSP compatibility and negative-origin enforcement | Packaged WebView2, Cocoa, WebKit console/network results |
| [#21](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/21) | Finish multi-file import end-to-end QA | 3 files / 2 directories, duplicates, revoked grants, single + batch exports, reports |
| [#22](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/22) | Sign/package actual binaries and run clean-machine release gate | Windows EXE/setup, Linux artifact, macOS app/DMG; hashes, signing/notarization truth |
| [#59](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/59) | Verify the native grant boundary in hostile cases | Unselected siblings, symlinks, ZIP members, auxiliary logos/fonts, write denial before dispatch |
| [#60](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60) | Finish independent format/renderer oracle matrix | Legitimate app-version samples, reference images, source hashes and full per-platform results |
| [#23](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/23) | Refresh product release/UX execution tracker | Measurable acceptance dossier across the other issues |

No source-only PR can establish all seven gates.

## 4. Priority roadmap — split into independently reviewable changes

### A. P0/P1 engineering quality, before a native candidate

1. **Typography overflow:** measure each specimen line using Pillow text bounds; shrink and, only at extreme lengths, truncate within available card width. Test long names and narrow font faces without relying on a specific OS font.
2. **Format-fixture coverage:** expand *deterministic synthetic smoke coverage* for standard formats, with explicitly labelled provenance and no claim of real authoring-app fidelity. Target at least 25 of 46 direct extensions in the next fixture milestone; keep strict/oracle checks fail-closed.
3. **Renderer memory/image fidelity:** add proof for depth ordering, UV texture sampling and transparent geometry before replacing the painter-based 3D renderer. Do not claim a z-buffer or physically-based rendering without image comparisons and bounded runtime tests.
4. **Native QA:** verify packaged builds on Windows/Linux/macOS, including DPI, preflight dependencies, bridge/CSP, grants, idle health, ZIP and CAD.
5. **Protect contributors' files:** ensure sidecar textures, logos, write destinations and scanned paths require native authorization; do not enable raw OS drag/drop paths without a picker confirmation/grant.

### B. P1 optional creator workflows (separate defaults and opt-ins)

- Bounded contact-sheet previews for multiple brush tips, artboards and animated frames; require explicit renderer-mode selection, per-image caps and no first-frame regression.
- An opt-in auto-frame/margin treatment that preserves aspect ratio, transparency semantics and existing output dimensions when disabled.
- Reusable brand presets with schema validation, explicit non-portable logo/font path handling and no authorization escalation.
- Optional tiled diagonal watermark only after independent opacity/coverage and marketplace-layout tests (built-in corner/center presets are already merged).

## 5. Local verification required before ready/release

At the exact candidate SHA, preserve stdout/stderr, OS architecture and artifact checksum:

```bash
python scripts/check_release_locally.py --mode full
python -m pytest tests/unit/test_creator_security_reaudit.py tests/unit/test_scene_material_preservation.py tests/unit/test_archive_mesh_cache_reaudit.py tests/unit/test_watermark_placement_reaudit.py -q
python scripts/audit_renderer_matrix.py --verify-fixtures
python scripts/audit_renderer_matrix.py --verify-fixtures --strict
```

The final strict command **must fail** while catalog coverage/oracles are incomplete. Never lower fidelity thresholds or self-generate reference oracles to force a green result. Run the OS-specific installer/portable tests and the exact-commit packaged renderer tests separately. Keep the existing signed release issue open until those results are checked.

## 6. PR rules and release semantics

- One engineering outcome per PR: mechanism, regression, limited scope, documentation, tests required.
- Record which checks were **actually executed**. The author of this report did not run native tests or a complete repository suite.
- Use `[skip ci]` for documentation and implementation PR commits while hosted CI minutes are constrained; the project owner runs full tests locally. Do not manually dispatch hosted workflows.
- Protect source ownership, native grants, and backward compatibility. Always distinguish **merged source**, **local tests passed**, **native packaged QA passed**, and **release certified**.
