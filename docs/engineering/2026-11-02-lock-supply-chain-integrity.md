# Dependency lock supply-chain integrity — 2 November 2026

## Verified finding

Current `main` (starting SHA `cffb21387850bb36e5e0af45f8cd7b0c988175fa`) includes **one** npm lock entry lacking integrity metadata:

- `frontend/package-lock.json` → `packages["node_modules/lenis"]`, version `1.3.27`
- Source URL: `https://registry.npmjs.org/lenis/-/lenis-1.3.27.tgz`
- **Missing:** `integrity: "sha512-..."`

The other 147 non-root npm lock entries have an integrity field. This missing checksum weakens reproducible artifact verification. **It is not evidence of a published vulnerability in Lenis, or proof of a Dependabot alert.**

Linked tracking issue: [#132](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/132).

The three Python locks currently share identical versions for every overlapping package, and each pinned package has at least one SHA-256 hash.

## New offline structural gate

`python scripts/verify_dependency_locks.py` validates:

1. Each pinned Python dependency has at least one correctly formatted SHA-256 artifact hash.
2. Runtime → development → Linux GUI locks retain the same package/version pairs wherever shared.
3. `frontend/package.json` and `frontend/package-lock.json` agree on top-level dependencies and devDependencies.
4. Each locked npm package declares a version, the expected trusted registry URL and a valid **format** for the SHA-512 integrity digest.

A correctly formatted checksum is **not sufficient proof of correctness**. The only reliable value is the digest provided by the actual trusted npm registry / retrieved tarball. Do not generate or insert guessed integrity values. This script never accesses the network, edits files or starts CI. It now runs as the first check of the opt-in `--security-audit` release validation flow.

### Expected result before the SRI fix

```
Dependency lock structural audit FAILED:
  - frontend/package-lock.json: node_modules/lenis missing SHA-512 integrity
```

This failure is intentional, and should persist until issue #132 is properly remediated. Do not suppress it or call the full security gate green.

## Owner: remedy with registry evidence

From `frontend/` on a trusted, network-connected machine:

```shell
npm view lenis@1.3.27 dist.integrity --registry=https://registry.npmjs.org
```

Use the registry's exact `sha512-...` string to restore the missing lock entry (or regenerate via npm and confirm it uses the same official SRI value). Do not change the package version unnecessarily, and preserve every other locked package's version and integrity.

Re-run:

```shell
npm ci
npm run typecheck
npm test
npm run build
cd ..
python scripts/verify_dependency_locks.py
python -m pytest tests/unit/test_dependency_lock_integrity.py tests/unit/test_local_release_gate.py -q
python scripts/check_release_locally.py --mode full --npm-ci --security-audit
```

The full local audit requires `pip-audit` installed in the audit environment, access to npm/PyPI advisory services and packages required by the application. Before a release, independently confirm its packaged WebView and rendering behavior on Windows and Linux, and later macOS.

## Boundaries

The offline gate does not audit GHSA/CVE entries. These still require the authenticated Dependabot alert export created by `scripts/dependabot_report.py`. Prioritize real critical/high vulnerable package/advisory pairs from that export; do not infer or dismiss alert status from this script. The new gate is intentionally opt-in and does not dispatch GitHub Actions.
