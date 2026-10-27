# PreviewGen Studio — PR conflict, engineering progress and release handoff

**Date:** 27 October 2026  
**Repository:** `mustaqeem66/Freepik-Preview-Generator` / branch `main`  
**Verified source snapshot:** `8a3d53bab8560518390dced6c6ac7a7cbe201594`  
**Scope:** owner's two uploaded audit notes plus live GitHub file, issue and PR review on this baseline.

## 1. Conflict resolution and actual PR state

**PR #103 is merged, not conflicted.** The previous synthetic-fixture branch was synchronized to `main` with exactly four intended files: `.gitignore`, `scripts/generate_synthetic_renderer_matrix.py`, `tests/unit/test_synthetic_renderer_matrix.py`, and `docs/engineering/2026-10-27-synthetic-smoke-matrix.md`. GitHub reports #103 merged at `ed91a9272c8e93bae399abaef97b098d6ff9ae55`. There is no conflict-resolution work for the owner on #103.

**Subsequent source PRs merged on this inspection:** #100 full release roadmap; #101 font specimen overflow; #103 synthetic renderer smoke matrix; #105 opt-in alpha subject auto-frame; #106 native picker error wording; #107 pending-native-evidence receipt with tests. #95–#99 previously merged the nine original source-level audit fixes.

**No PR merge equals native release certification.** Local Python/frontend suites and real installed apps were not executed by this author; some merges occurred concurrently while reviewing. Do not reinterpret `mergeable=true` or a successful merge as a passed test.

## 2. Open PR decision guide at this snapshot

| PR | Scope | Recommended disposition | Owner's test before merge |
|---|---|---|---|
| [#91](https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/91) | Dependabot: `actions/checkout` v4.2.2 → v7.0.1, SHA pinned | **Hold pending workflow compatibility review** (major action update). Recheck diff against latest `main`; especially Windows, Ubuntu and macOS | Validate checkout functionality with a locally executed compatible GitHub Actions runner or isolated test, then only restore hosted CI when explicitly approved. Never infer success from mergeability. |
| [#93](https://github.com/mustaqeem66/Freepik-Preview-Generator/pull/93) | Dependabot: `lucide-react` 1.59.0 → 1.61.0, with lockfile | **Review after local frontend verification**; low-scope dependency change but may conflict with later `package-lock.json` edits | From that PR's exact SHA: `npm ci`, `npm run typecheck`, `npm test`, `npm run build`. Check icon imports and rendered controls. |

PR #92 (`actions/setup-python`) and PR #94 (Vite) were verified merged before this document was written. They do not need another merge. Verify all statuses live again at the moment of action: Dependabot may rebase, and other maintainers can merge or update in parallel.

**CI-minutes constraint:** do not trigger GitHub Actions manually. A normal merge to `main` can start the configured build workflow, so explicitly plan hosted usage and commit-message skip behavior before merging dependency PRs.

## 3. Audit remediations and product enhancements

- **Original nine issues:** source remediations committed in PRs #95–#99; source tests extended through #97. Windows/Linux/macOS packaged regression verification is outstanding.
- **Typography clipping:** #101 fits and truncates wide specimen text; real font formats and display sizes still need native smoke.
- **Renderer sample coverage:** #103 generates 19 synthetic inputs in addition to the 12 existing fixture files. The original committed samples cover 11/46 distinct previewable extensions; **at least 25 distinct suffixes can be generated for smoke testing**, not certified real app versions.
- **Alpha subject framing:** #105 adds default-off `autoFrame` and 0–25% margins, preserves canvas dimensions and limits enlargement; actual preview/export QA still pending.
- **Native picker guidance:** #106 closes the leftover catch-path suggestion to paste paths that had contradicted native read-grant rules.
- **Native release evidence:** #107 adds `scripts/native_release_evidence.py`. It records all QA gates as `pending` initially, checks exact SHA-256 digests, and cannot substitute for real native tests or independently reviewed visuals.

## 4. Release-blocking issues (remain OPEN until verified)

- [#19](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/19) — Windows idle freeze: root cause and reproducible native proof.
- [#20](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/20) — packaged CSP/WebView2-Cocoa-WebKit bridge and blocked-origin negative test.
- [#21](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/21) — native Add Files multi-directory, permission revocation, batch and report acceptance.
- [#22](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/22) — actual package installation, signing/notarization, checksums and release proof.
- [#59](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/59) — hostile source-read/export-write/picker/ZIP/symlink security cases.
- [#60](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60) — 46-extension matrix with real lawful app samples and *independent* visual oracles.
- [#23](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/23) — umbrella product/UX and release execution tracker.

## 5. Next recommended PRs (do not conflate with implementation done)

1. **P0 native acceptance:** installed Windows, Linux and macOS verification against one exact binary/commit using `scripts/native_release_evidence.py`. Include 300-second Windows idle, high DPI, CSP negative origins, denied file grants, ZIP and 3D/CAD, cancellation, upgrade/uninstall, true signing evidence.
2. **P1 renderer realism:** independent baseline vs new 3D depth-order/UV-mapped material rendering with realistic bounded geometry, image-oracle comparisons and cancellation/performance budget before enabling new mode. Current per-part flat color is not PBR.
3. **P1 formats:** genuine app-produced proprietary and CAD files, real reference images and failure classification; synthetic fixtures may find parser regressions but cannot prove fidelity.
4. **P1 workflow:** bounded creator contact sheets/animation previews, opt-in brand presets with explicitly validated assets, secure native drop authorization. Keep opt-ins backwards compatible.
5. **P2 polish:** tiled watermark/composition with pixel oracles; verify quality and batch consistency.

## 6. Local execution instructions (not claimed executed)

```bash
python scripts/check_release_locally.py --mode full
python -m pytest tests/unit/test_font_specimen_fitting.py tests/unit/test_synthetic_renderer_matrix.py tests/unit/test_auto_frame_subject.py tests/unit/test_native_release_evidence.py -q
python scripts/generate_synthetic_renderer_matrix.py --output-dir local-fixtures
python scripts/audit_renderer_matrix.py --manifest local-fixtures/renderer-samples.json --fixtures-dir local-fixtures --verify-fixtures --report local-fixtures/audit.json
```

For frontend, from `frontend/`: `npm ci && npm run typecheck && npm test && npm run build`. The strict oracle matrix intentionally fails until all real-format evidence exists.

For native receipts, see `docs/engineering/2026-10-27-native-evidence-handoff.md`. **Never** edit evidence to say passed merely because a source PR merged, and never publish machine-specific QA logs by default.

**Status discipline:** source merged / unit suite passed / packaged native QA passed / independently certified / ready to release are separate gates. Re-check the current PR state after this snapshot before approving or merging anything.
