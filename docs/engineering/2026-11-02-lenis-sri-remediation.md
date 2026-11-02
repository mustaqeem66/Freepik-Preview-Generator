# Finish the missing Lenis npm checksum repair locally

The main branch's `frontend/package-lock.json` has a `node_modules/lenis`
entry for `1.3.27` with an npm registry tarball URL but no `integrity`
field. GitHub issue [#132](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/132)
tracks the fix. This is a *supply-chain integrity* gap, **not** a known CVE.

A checksum value must come from npm's registry and match the actual
tarball. This assistant's environment cannot access the npm registry.
No fake checksum has been inserted into the repository.

## Automated local repair

From an updated checkout of this PR's branch on a trusted Windows or Linux machine:

```shell
python scripts/repair_lenis_integrity.py
python scripts/repair_lenis_integrity.py --apply
git diff -- frontend/package-lock.json
```

The first command is offline and read-only; it currently reports that the
integrity value is absent. The second explicitly uses the npm CLI to query
`lenis@1.3.27` `dist.integrity` at `https://registry.npmjs.org`
over TLS, accepts only a base64-encoded 64-byte SHA-512 digest, and
atomically writes it into the lock. It refuses to replace an existing
different checksum or modify a changed version/registry URL. Other
packages retain their versions. Do not run `--apply` on an untrusted
network or with a spoofed local npm binary.

The resulting lock diff should show only the missing integrity field.
Review it before committing, and do not accept unrelated dependency changes.

## Local acceptance (both platforms)

```shell
cd frontend
npm ci
npm run typecheck
npm test
npm run build
npm audit --package-lock-only --audit-level=low --include=dev
cd ..
python -m pytest tests/unit/test_repair_lenis_integrity.py -q
python scripts/verify_dependency_locks.py
python scripts/check_release_locally.py --mode full --npm-ci --security-audit
```

`verify_dependency_locks.py` is provided in separate PR #133; if that
PR has not merged, use its branch for that command. `--security-audit`
also requires `pip-audit` installed in your validation Python environment
and network access to advisory registries. Do not manually run GitHub
Actions. After verified local checks, push the one-entry lock diff as a
small security PR and close issue #132 only once it is merged.

The private Dependabot advisory list still needs the authenticated export
from `scripts/dependabot_report.py`; restoring SRI is not a substitute
for GHSA/CVE-specific fixes.
