# Dependabot vulnerability triage — 2026-11-02

## Status and evidence limits

The security dashboard at `Security > Dependabot` is **not public** even for a public repository. This change does not assert that any vulnerability is fixed, does not dismiss alerts, and does not modify dependencies. To fix a specific alert, capture its current severity, ecosystem, affected manifest, package, vulnerable range, patched version, and GHSA/CVE using the authenticated read-only API.

The repository currently has hash-pinned Python runtime, development, and Linux GUI lock files and an npm v3 lock file in `frontend/`. Never manually edit Python hashes or ship an unverified npm lock file.

## Step 1 — export every open alert without uploading secrets

Install and authenticate the GitHub CLI (`gh auth login`) locally, with access to this repository's security alerts. Then, from the repository root, run:

```shell
python scripts/dependabot_report.py --format markdown --output dependabot-open-alerts.md
python scripts/dependabot_report.py --format json --output dependabot-open-alerts.json
```

The script fetches *all pages* with GitHub's authenticated read-only REST endpoint. It outputs only package, manifest, range, fix version, severity, GHSA and URL fields. No tokens are saved. Do **not** commit exported alert files; use them locally or share privately with a maintainer. If access is denied, obtain Dependabot alert access instead of declaring zero issues. `--input path/to/gh-export.json` supports offline triage without GitHub access.

## Step 2 — resolve one advisory at a time

1. Sort by critical/high severity and real reachable/runtime impact, not just alert count. A missing `firstPatchedVersion` is **not** permission to assume safety.
2. Identify which of `requirements-lock.txt`, `requirements-dev-lock.txt`, `requirements-linux-gui-lock.txt`, `frontend/package-lock.json` or a GitHub Actions workflow was flagged.
3. For Python, update source constraints in `requirements.in` / `requirements-dev.in` only where necessary. Regenerate all affected SHA-256 hashed locks with `uv pip compile --universal --generate-hashes --python-version 3.12`, preserving the Linux GUI constraint on PyGObject. Do not bypass `--require-hashes` or hand-edit hashes.
4. For npm, update the required direct version (if direct) and regenerate `frontend/package-lock.json` through npm. Avoid `npm audit fix --force` unless major-version and application compatibility impacts have been reviewed.
5. Make one PR per unrelated package/advisory family, including GHSA/CVE reference and exact before/after version, manifest and regression test. Use `[skip ci]` in commits; run the test plan locally rather than dispatching GitHub Actions.
6. Re-export the open alerts after merging; a merge alone is not proof an alert has closed. Do not dismiss a real alert to make the count look better.

## Step 3 — local validation (Windows PowerShell or Linux/macOS shell)

```shell
python -m pip install --require-hashes -r requirements-dev-lock.txt
python -m pytest tests/unit/test_dependabot_report.py -q
python scripts/check_release_locally.py --mode full --npm-ci
```

For *advisory* scans, install `pip-audit` in a separate audit environment and run it against each pinned lock, then run npm's registry-backed audit:

```shell
pip-audit --require-hashes -r requirements-lock.txt
pip-audit --require-hashes -r requirements-dev-lock.txt
pip-audit --require-hashes -r requirements-linux-gui-lock.txt
cd frontend
npm audit --package-lock-only --audit-level=low
```

These commands require network registry access and may return findings that are not yet visible in Dependabot; keep the complete scanner evidence. On Windows and Linux verify the actual packaged runtime separately. macOS release certification remains separate until native evidence exists.
