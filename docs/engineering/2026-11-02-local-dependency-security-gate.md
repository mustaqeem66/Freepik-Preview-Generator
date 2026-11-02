# Optional local dependency security gate — 2026-11-02

The existing local release planner does not currently check dependency vulnerability databases. This PR adds a **read-only, opt-in** `--security-audit` flag. Existing default release checks remain unchanged.

## Scanned artifacts

- `requirements-lock.txt` — Python runtime packages.
- `requirements-dev-lock.txt` — Python runtime and build/test packages.
- `requirements-linux-gui-lock.txt` — Linux GUI packaging packages.
- `frontend/package-lock.json` — npm dependencies, explicitly including `devDependencies` (Vitest, Vite, test tooling).

Python checks use `python -m pip_audit --require-hashes -r <lock>`. npm uses `npm audit --package-lock-only --audit-level=low --include=dev`. Both consult external advisory feeds and **must not be run offline**. Neither command edits the dependency files, installs upgrades, dismisses GitHub alerts, or runs GitHub Actions. Findings or unavailable audit tools yield a nonzero local release result.

## Setup and execution

Within the Python environment you use for release validation, install the separately managed `pip-audit` audit tool using your normal trusted package source. This security checker is intentionally **not** added to the frozen application's hash-pinned production dependencies.

From the repository root on Windows PowerShell, Linux, or macOS:

```shell
python scripts/check_release_locally.py --mode full --npm-ci --security-audit
```

To isolate scope and shorten troubleshooting:

```shell
python scripts/check_release_locally.py --backend-only --security-audit
python scripts/check_release_locally.py --frontend-only --npm-ci --security-audit
python -m pytest tests/unit/test_local_release_gate.py -q
```

Use the generated `local-check-report.json` as a **local** summary of pass/fail checks, not as proof that GitHub's private Dependabot dashboard is clear. All checks run on the current host; the universal Python lock files can include different platform-marker branches, so repeat relevant Python audits on Windows/Linux (and macOS before certification). A zero-vulnerability scan does not prove no other security problems exist.

## Remediation discipline

Work one GHSA/CVE and package family per PR; update the direct source constraint when necessary, recompile Python universal hashed locks rather than editing hashes, and regenerate npm's lock with npm. Review breaking upgrades against the app's actual rendering and packaging tests. Repeat the advisory scan **after** merging and independently verify the corresponding Dependabot alert has closed.

No GitHub Actions are required by this change. The optional gate is part of the manually invoked local command only.
