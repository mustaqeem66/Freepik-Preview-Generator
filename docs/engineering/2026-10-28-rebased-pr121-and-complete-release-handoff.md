# PreviewGen Studio — reconciled audit, PR #121 rebase and 100% release roadmap

**Date:** 28 October 2026  
**Repository/branch:** `mustaqeem66/Freepik-Preview-Generator` / `main`  
**Inspected baseline:** `b10dde473837c279cd18ec8338c3ffa626b65b0c` (refresh live GitHub status before merging or signing off).  
**Uploaded reports:** `Pasted markdown(6).md` and `Pasted markdown(2).md` are byte-identical (SHA-256 `58cbd0673e362da886bfb6aba8bc42bd87dc7e8fa3f2b7b001efe8c3e76f08e4`). The report is historical: source line numbers and its 'currently present' defects describe an earlier revision, not this baseline.

## 1. PR conflicts — factual resolution and owner instructions

| PR | Status on this review | Action |
|---|---|---|
| [#103](https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/103) | **Merged** at `ed91a9272c8e93bae399abaef97b098d6ff9ae55` | No merge conflicts or action remaining. The `/conflicts` URL is historical. |
| [#115](https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/115) | Merged | No further merge; brushset sheet needs real-app QA. |
| [#116–#120](https://github.com/mustaqeem66/Freepik-Preview-Generator/pulls?q=is%3Apr+is%3Amerged) | Merged | Style presets, bounded CPU z-buffer and isolated UV texture-kernel regressions are source-merged, **not full production 3D certification**. |
| [#121](https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/121) | **Open, mergeable** after conflict rebase | The branch `fix/ci-regressions-font-typecheck-tempfiles-20261028` was reconstructed as a single commit `1c5e8995d18004cb767bbc252f5bce19d4b2953b` on the then-current `main` `3442a14b85bd85ca4cef7205e70974405a531a77`. Re-run local suites **on this new exact head** before merging. |
| [#123](https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/123) | Merged | Source-oracle provenance hardening landed. Metadata checks still cannot prove a claimed real source application is truthful. |

**#121 reconciliation details:** applied all 14 patch files to the correct current base, preserving later Windows Authenticode release-gate requirements, the Procreate brushset contact sheet and merged 3D z-buffer/UV work. Previous #121 PR-body testing numbers refer to an *earlier* head and cannot be used as proof for the rebased commit. GitHub reported `mergeable=true` following the update.

**CI minutes:** No GitHub Actions were manually dispatched for this work. Commits were marked `[skip ci]`; the owner should still check workflow triggers and run local parity before accepting a merge.

## 2. Re-check of the nine original source discrepancies

| Historical source audit finding | Current source disposition | Evidence still needed |
|---|---|---|
| Untextured 3D model color not invalidating live previews | Source-fixed in #95 with hook coverage | Native orbit/color rerender with actual meshes |
| Local Windows PyInstaller missing required DAE/3MF engines | Source build script/env checks synchronized in #95 | Fresh Windows installed/portable binary render smoke |
| Environment verifier missing mandatory engines | Source-fixed in #95 | Local locked-dependency and packaged import check |
| ZIP 3D/CAD orbit cache missing due to temporary extraction identities | Source-fixed in #98 | Archive orbit latency and invalidation in native app |
| Krita missing-preview error and nested .brushset ZIP check bypass | Source-fixed in #96, later brushset grid #115 | Proprietary-version samples, ZIP abuse and genuine creator files |
| Unbounded Maya .ma thumbnail line and split base64 | Source-fixed in #96 | Large-line and real Maya thumbnail samples |
| Material loss on multi-node `trimesh.Scene` concatenation | Source-fixed in #96 | Independent material and real 3D visual oracles |
| Contradictory folder-paste UI/help guidance | Source-fixed in #95; stray picker-error advice corrected in #106 | Installed OS native permission prompts and negative tests |
| Orphaned diagnostic/help menu; inaccessible watermark position presets | Presets exposed in #99 and diagonal tiles #109. The diagnostic-button suggestion was **intentionally not implemented** to honor the premium no-extra-debug-controls UI direction | Accessible keyboard commands, discoverability and live preview |

These are **source-remediated**, not independently certified or universally correct for every application/OS.

## 3. Additional source improvements since the report

- #101: measured text fit in font specimen cards; PR #121 refines narrow-canvas margins.
- #103: 12 committed source samples plus a reproducible local synthetic generator with 19 new examples covering at least 25 distinct format suffixes **for smoke only**; baseline committed fixtures still cover 11 distinct extensions.
- #105: optional alpha subject normalization, default disabled.
- #107/#110: fail-closed native QA receipts tied to exact binaries and proper Windows signing requirements.
- #109: optional tiled watermark.
- #111/#115: bounded GIF/WebP temporal and Procreate brushset multi-tip contact sheets.
- #112: bounded reads of large embedded DWG and 3ds Max previews.
- #116: local reusable visual presets with native file path/grant exclusion.
- #117/#119/#120: standalone depth and UV rasterizer CPU kernel and regression tests. **Production mesh renderer still uses the painter-based path; real PBR/perspective/alpha/oracle work is not complete.**
- #123: rejected openly synthetic, unknown, PreviewGen-authored or same-source oracle provenance.

## 4. Remaining release gates (none closed by source-only PRs)

| Priority | GitHub issue | Required acceptance proof |
|---|---|---|
| P0 | [#19 Windows idle freeze](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/19) | Root-cause trace, 300-second idle/scan/cancel/repeat at 100–200% DPI on installed and portable WebView2 builds |
| P0 | [#59 Native grant security](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/59) | Negative attempts against sibling/renamed/symlinked files, ZIP members, revoked grants, fonts/logos, selected-file export paths |
| P0 | [#22 Signed desktop release](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/22) | Clean-machine Windows EXE/setup and Authenticode, Linux AppImage, macOS DMG codesign/notarization/Gatekeeper; SHA-256 artifacts |
| P1 | [#20 CSP/WebView](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/20) | Packaged WebView bridge success plus explicitly blocked external-origin attempts |
| P1 | [#21 Multi-file import](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/21) | Three files/two folders, duplicates, removal, denied file grants and source-preserving batch receipts |
| P1 | [#60 Format/renderer visual oracles](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60) | Real lawful third-party source-application files, versioned independent reference images, quality/error thresholds, cross-OS results for all 46 direct formats |
| Umbrella | [#23 Studio v2.2](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/23) | Reconcile UX, performance, security and release gates at one candidate commit |

## 5. Still missing from the extended feature roadmap

1. Finish production 3D integration: bounded depth ordering, actual per-fragment UV, multiple materials and correct fallback, transparent surfaces, perspective and shading; measure native latency and independent visuals.
2. Real version-specific Illustrator/InDesign multiple-page/artboard handling where format legally and technically permits it; clarify thumbnail-only unsupported versions.
3. Secure native drag-and-drop **only after** proving dropped source paths go through a trusted OS permission/grant flow; DOM path strings alone must never authorize access.
4. User-editable font specimen phrase with length and layout bounds, if it fits product scope.
5. Finish installer, high-DPI, CSP, freeze/root-cause and file-grant verification; no feature polishing should bypass P0 work.

## 6. Required local tests at an exact commit

For **PR #121**, switch to `fix/ci-regressions-font-typecheck-tempfiles-20261028` and record the new head `1c5e8995d18004cb767bbc252f5bce19d4b2953b`. Then run:

```bash
python -m ruff check .
python -m pyrefly check
python -m pytest tests/ -q
python scripts/check_release_locally.py --mode full
python scripts/verify_environment.py
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

Validate the merge destination has not moved before approving; if new changes touch the same paths, reconcile again rather than dropping either side.

For release candidates on Windows, Linux and eventually macOS: use `scripts/native_release_evidence.py init` to record all platform gates as pending, collect authentic redacted logs/videos/artifact digests, then use `verify`. Reviewers must independently validate signed artifacts and real visual oracle provenance. No synthetic sample or self-generated renderer output should be presented as the source application's approved oracle.

**PM acceptance rule:** source merged ≠ local unit tests passed ≠ packaged cross-platform QA passed ≠ independent render fidelity certified ≠ signed release ready. The 7 issues stay open until the last four conditions have reproducible evidence.
