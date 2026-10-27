# PreviewGen Studio — Re-audit, development progress, PR disposition and release handoff

**Snapshot: 28 October 2026 (Asia/Karachi).** Repository: `mustaqeem66/Freepik-Preview-Generator`. Baseline `main`: `1cbb21d9c6d845fdad6fcf51505411032e4c77ef`. This is an engineering **source-status and acceptance-plan record**, not a certificate of desktop installation or shipping quality.

## GitHub PR decisions

- **#103: MERGED.** Its original conflicts have been resolved. Owner does not need to open the conflicts page or cherry-pick it.
- **All pull requests through #125: merged** at the time of this re-audit. Do not remerge closed items or leave obsolete Dependabot PRs open.
- **#126, MERGED:** pre-parse mesh line/GLB/glTF input memory hardening. Focused local tests still required: `tests/unit/test_mesh_inspection_read_bounds.py` + `tests/unit/test_resource_limits.py`.
- **#127, MERGED:** strict independent evidence files in native release receipt. Focused local tests still required: `tests/unit/test_native_release_evidence.py`.
- **#128, MERGED:** this reconciled audit and PR disposition document. At this snapshot there are **zero open PRs**. None of these merges authorizes a stable release; exact-commit local and packaged-native acceptance is still outstanding.

## Source implementation progress since the original audit

The two user-supplied markdown reports are byte-identical. Both describe the earlier v2.1.2 source state and correctly identify nine initial defects for that baseline. The newer `main` has advanced through PRs #95–#125.

| Audit area | Source-level disposition | Remaining proof |
|---|---|---|
| Live preview ignores 3D model color | Addressed by merged 95–99 remediation family | Live Windows/Linux/macOS orbit/color QA |
| Local Windows missing COLLADA/lxml/networkx packaging | Source build/dependency parity addressed | Installed/portable binary format smoke |
| Incomplete environment dependency verification | Source verification repaired | Run full environment tests locally |
| ZIP mesh cache keyed on ephemeral extract path | Archive identity/cache remediation merged | Orbit benchmark and invalidation on ZIP mutation |
| Krita and nested brush ZIP error/resource bounds | Source remediation merged | Genuine creator-file versions and hostile archives |
| Maya ASCII thumbnail unbounded line / fragmented base64 | Source remediation merged | Genuine Maya assets; malformed/oversize negative cases |
| trimesh mixed-node visual loss | Per-part normalization merged | Independent mixed-scene accuracy oracles |
| Misleading folder-path paste instructions | Native picker guidance revised | Packaged native picker usability |
| Help access and watermark preset wiring | Source UI/settings repairs merged | End-to-end WebView/preview/batch consistency |

Additional merged contributions: #100 and later progress plans; #101 font auto-fit; #102–#103 reproducible **synthetic** 25+ format smoke matrix; #104–#105 opt-in subject framing; #106 native picker error guidance; #107 and #110 evidence/signing ledger; #109 tiled watermark; #111 animation contact sheets; #112 bounds on MAX/DWG thumbnail reads; #114 JSX hotfix; #115 bounded Procreate brushset contact sheets; #116 **grant-free** style presets; #117 CPU z-buffer *prototype*; #119 bounded CPU UV-sampling *prototype*; #120 regressions; #121 linter/type/test follow-ups; #122–#123 reject self-certified/synthetic renderer oracles; #125 reject oversized UV/color input arrays.

**Do not overclaim:** the CPU z-buffer/UV kernel is isolated and is not yet the proven production 3D renderer. JPEG-based previews cannot represent interactive native scene fidelity, and source merges alone cannot prove app installation, security, PBR shading or proprietary file support.

## Remaining release issues and required independent acceptance

| Issue | Required verified native evidence | Priority |
|---|---|---|
| [#19](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/19) | Windows installed+portable reproducible freeze investigation, real thread evidence, 300s idle, 100–200% DPI and actual root-cause confirmation | P0 |
| [#59](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/59) | OS picker-granted exact source vs unapproved sibling, symlink/ZIP revocation, auxiliary font/logo and output write negative proofs | P0 |
| [#22](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/22) | Signed Windows binaries, real macOS notarization and Linux QA, artifact digests, executable installer, uninstaller and native tests | P0 |
| [#20](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/20) | Real Windows WebView2, macOS Cocoa, Linux WebKit CSP bridge+blocked-origin behavior | P1 |
| [#21](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/21) | Three Add Files from two directories; deduplication, revoke, preview/export, cancellation and report provenance across OSs | P1 |
| [#60](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60) | Licensed independently approved authoring-app/version examples and visual oracles for CAD/3D/proprietary formats; strict oracle gate | P1 |
| [#23](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/23) | Product, premium UX/accessibility, release tracking umbrella. Close last | Tracker |

## Exact local test sequence for latest merged engineering fixes

Both source PRs have merged into `main`. Run focused tests on the exact merged revision, not on outdated draft branches.

```bash
git fetch origin
git switch main
git pull --ff-only
python -m pytest tests/unit/test_mesh_inspection_read_bounds.py tests/unit/test_resource_limits.py tests/unit/test_native_release_evidence.py -q
```

After review and integration onto a single fixed `main` commit, run:

```bash
python scripts/check_release_locally.py --mode full
python scripts/verify_environment.py
python scripts/generate_synthetic_renderer_matrix.py --output-dir local-fixtures
python scripts/audit_renderer_matrix.py --manifest local-fixtures/renderer-samples.json --fixtures-dir local-fixtures --verify-fixtures --report local-fixtures/audit.json
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

The synthetic render audit is a smoke test only, **never** independent source-app fidelity proof. Native Windows/Linux/macOS validation requires the actual packaged desktop application, independent QA evidence, source SHA, installer signature/provenance and artifact SHA-256. Preserve redacted logs, isolated negative security tests and human approval. Windows/Linux local test results may be supplied by the owner; macOS remains a distinct later acceptance task. Do **not** manually trigger GitHub Actions; commits in this effort use `[skip ci]`.

## Definition of 100%

“100%” means: no unresolved P0 safety/release blockers; every advertised format is described honestly; all supported native-platform acceptance checklists on a fixed commit have independent signed-off evidence; and tests + actual binary behavior pass. It is **not** 100% success inferred from PR merges or an engineering maturity percentage.

**Work not claimed completed by this report:** Windows idle-freeze cause, fully integrated PBR quality, genuine licensed oracles for every advertised format, packaged OS CSP behavior, signing/notarization or release certification.
