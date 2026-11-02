# Lenis integrity remediation — Windows executable fix (3 Nov 2026)

## Verified code-path risk

The previous `repair_lenis_integrity.py --apply` invoked bare `npm` as an argument-array subprocess. On Windows Node.js typically installs an `npm.cmd` command shim rather than `npm.exe`. The local release checker already resolves the executable via `shutil.which("npm")`; this patch applies the same resolution to the integrity repair. It rejects a missing executable without attempting a network request or touching the lockfile.

This change **does not** insert a SHA-512 hash into `frontend/package-lock.json` and does not claim that issue #132 or a Dependabot vulnerability is resolved.

## Local Windows PowerShell

```powershell
git switch main
git pull origin main
where.exe npm
python -m pytest tests/unit/test_repair_lenis_integrity.py -q
python scripts/repair_lenis_integrity.py --apply
python scripts/verify_dependency_locks.py
git diff -- frontend/package-lock.json
```

Only accept the diff if it adds the `integrity` field to `node_modules/lenis` with the publisher-reported SRI. Do not fabricate or paste an unverified digest. Follow with:

```powershell
cd frontend
npm ci
npm run typecheck
npm test
npm run build
npm audit --package-lock-only --include=dev --audit-level=low
```

The SHA-512 hash and native packaging still require real local registry and host validation. No GitHub Actions need to be started.
