# PreviewGen Studio — 28 October 2026 audit verification and engineering execution report

**Repository:** `mustaqeem66/Freepik-Preview-Generator`  
**Target:** `main`, inspected revision `1121e31a5805e61474a0443fd7e3bef2c0ff3024`. Snapshot only; refresh PR and branch status before applying this plan.  
**Source report:** owner-uploaded `Pasted markdown(6).md` and `Pasted markdown(2).md`, SHA-256 `58cbd0673e362da886bfb6aba8bc42bd87dc7e8fa3f2b7b001efe8c3e76f08e4` (byte-identical).  
**Execution rule:** no hosted GitHub Actions intentionally run; user will execute full CI on local Windows/Linux. macOS native smoke remains outstanding.

## 1. PR #103 and other open PRs — factual state

- PR **#103** is **MERGED**, not conflicted. Its synthetic multi-format smoke fixtures were rebased and merged under `ed91a9272c8e93bae399abaef97b098d6ff9ae55`. The `/pull/103/conflicts` URL does not indicate an active merge conflict.
- The previous open draft **#115**, bounded multi-tip Procreate brushset contact sheets, is **MERGED** and needs no further merge.
- Before this new development round, the GitHub open pull-request list was empty.
- **PR #116 (new, draft):** secure, browser-local style presets with strict no-path/no-grant allowlist, UI save/apply/delete, size limits and frontend regression tests.
- **PR #117 (new, draft):** independently testable, bounded NumPy depth-buffer rasterizer kernel; production 3D renderer unchanged pending independent visual proof.
- This documentation PR is a separate milestone. PR state can change in parallel; recheck GitHub when local CI results are ready.

## 2. Original audit finding disposition

The original report's nine code discrepancies were remedied in source PRs **#95–#99** and follow-ups. Specific merged source behavior includes: live model-color invalidation; Windows render dependency bundling and environment checks; archive mesh-cache identity; bounded creator ZIPs and Krita missing-thumbnail diagnostics; bounded Maya ASCII scanning; mixed scene material normalization before combining; read-only native folder picker wording; and accessible built-in object-centered/corner watermark presets. The orphaned Help/Diagnostics button recommendation was intentionally reconciled with the product requirement to avoid exposing extra diagnostic UI buttons.

Additional merged work: **#101** font specimen text fitting; **#103** synthetic 25+ format-path generation without oracle claims; **#105** default-off transparent subject framing; **#107/#110** release receipts and signing gate; **#109** optional diagonal tiled text; **#111** optional GIF/WebP nine-frame sheet; **#112** bounded DWG/3ds Max embedded thumbnail reads; **#115** optional brushset multi-tip sheet.

**What has not been proved by these source merges:** real format fidelity, Windows/Linux/macOS installer operation, native permission denial tests, independent reference image matching, signing/notarization, the Windows hang root cause, or full 46-format certification.

## 3. Remaining work, by priority

| Priority | Owner issue / workstream | Real acceptance requirement |
|---|---|---|
| **P0** | [#19 Windows freeze](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/19) | Capture installed/portable WebView2 stall trace, reproduce after 300-second idle, cancel/scan/preview loop at multiple DPI levels, fix verified root cause |
| **P0** | [#59 Native grants](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/59) | Deny source siblings, revoked paths, symlinks, malicious ZIP members, unauthorized auxiliary fonts/logos and export targets in packaged applications |
| **P0** | [#22 Native release](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/22) | Exact commit/artifact hashes, Windows Authenticode, Linux AppImage QA, macOS codesign/notarization and Gatekeeper proof, no unsigned release waiver |
| **P1** | [#20 WebView CSP](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/20) | Packaged WebView2/WebKit/Cocoa bridge, negative external-origin requests, console/network evidence |
| **P1** | [#21 Add Files](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/21) | Three files from two folders, duplicates, denied grants, single/batch outputs and reports |
| **P1** | [#60 Renderer oracle](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60) | Independent application-version-produced lawful assets and human-approved image references for every advertised format; strict, isolated visual comparison |
| **P1** | Depth/texture/PBR | Integrate proven z-buffer with UV sampling and mixed-scene materials only after bounded image-oracle regression and performance measurements |
| **P2** | Creator/marketplace workflow | Multi-page AI/InDesign sample verification, native-confirmed drag/drop, font custom sample text, grant-safe styling presets and dark/light UX acceptance |
| **Umbrella** | [#23](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/23) | Keep project tracker open until all preceding independent gates are signed off |

## 4. Immediate PR handoff

**#116 local review:** checkout `feat/grant-safe-style-presets-20261028` and run `cd frontend && npm ci && npm run typecheck && npm test && npm run build`. Verify that saving/applying a style never changes or reauthorizes `logoPath`, `fontPath`, `inputFolder`, `outputFolder`, or the native export permission. Test corrupt/quota-denied storage and keep the UI user-facing rather than diagnostic-heavy.

**#117 local review:** checkout `feat/bounded-software-zbuffer-proof-20261028` and run `python -m pytest tests/unit/test_depth_rasterizer.py -q`, `python -m ruff check .` and `python scripts/check_release_locally.py --mode full`. Confirm frontmost depth under reversed face order, interpolated occlusion crossing, invalid inputs and pixel-work limits. This is an isolated correctness building block; **do not certify production 3D fidelity** from these tests.

Both PRs require the full local release suite at their exact checked-out commit before being marked ready or merged. For isolated work branches, use separate local checkouts; do not run their tests indiscriminately on `main` before merge.

## 5. Existing local release commands and evidence

```bash
# Exact committed source, Windows and Linux locally:
python scripts/check_release_locally.py --mode full
python scripts/verify_environment.py
python scripts/generate_synthetic_renderer_matrix.py --output-dir local-fixtures
python scripts/audit_renderer_matrix.py --manifest local-fixtures/renderer-samples.json --fixtures-dir local-fixtures --verify-fixtures --report local-fixtures/audit.json

# Frontend:
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

Use `scripts/native_release_evidence.py` with real binary checksums, redacted native logs and signed reviewer outcomes; every native acceptance gate starts pending. The **strict** renderer-oracle mode is supposed to fail until real fixtures, independent approved images and all formats pass. Do not modify thresholds, waive security requirements, or self-generate a renderer's oracle.

## 6. Verified vs unverified evidence

**Verified in this continuation:** both audit uploads byte-identical; GitHub PR #103 and #115 merged; empty open-PR list at baseline; real source implementations of opt-in animation, brushset, alpha framing and tiled watermark; PR #116/#117 source branches and authored tests; isolated Python/NumPy pixel-depth ordering example (front color wins both draw orders and depth crossing). **Not executed:** full Python/frontend project tests, signed installer/native QA, independent source-application image oracle suite or macOS build verification. Source implementation maturity is not a release pass rate.

**PM decision:** Prioritize native #19/#59/#22 and real #60 oracles over claiming 100% from merged PRs. Keep seven release issues open until objective exact-commit/native evidence exists.
