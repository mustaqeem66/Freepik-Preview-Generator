#!/usr/bin/env python3
"""Offline structural integrity check for the repo's checked-in dependency locks.

This is NOT an advisory scanner or a replacement for npm/pip-audit; it checks
that dependency manifests agree and locked artifacts have integrity metadata.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_LOCK = "requirements-lock.txt"
DEV_LOCK = "requirements-dev-lock.txt"
LINUX_LOCK = "requirements-linux-gui-lock.txt"
PYTHON_LOCKS = (RUNTIME_LOCK, DEV_LOCK, LINUX_LOCK)

# uv's generated, SHA-256-hashed pip lock files use one pin per heading.
PYTHON_PIN = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)(?:\[[^\]]+\])?==([^\s;\\]+)")
SHA256 = re.compile(r"--hash=sha256:[0-9a-f]{64}(?![0-9a-f])")
NAME_NORMALIZE = re.compile(r"[-_.]+")
TRUSTED_NPM_REGISTRY = "https://registry.npmjs.org/"


def normalize(name: str) -> str:
    return NAME_NORMALIZE.sub("-", name).lower()


def parse_python_lock(path: Path) -> tuple[dict[str, str], list[str]]:
    issues: list[str] = []
    pins: dict[str, str] = {}
    current: tuple[str, int] | None = None
    hashed = False

    def finish() -> None:
        if current is not None and not hashed:
            issues.append(f"{path.name}:{current[1]}: {current[0]} lacks SHA-256 hashes")

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = PYTHON_PIN.match(line)
        if match is not None:
            finish()
            name, version = normalize(match.group(1)), match.group(2)
            if name in pins:
                issues.append(f"{path.name}:{lineno}: duplicate {name} pin")
            pins[name] = version
            current, hashed = (name, lineno), False
        elif current is not None and SHA256.search(line):
            hashed = True
    finish()

    if not pins:
        issues.append(f"{path.name}: no SHA-256-hashed Python package pins found")
    return pins, issues


def npm_issues(manifest_path: Path, lock_path: Path) -> list[str]:
    problems: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages")
    if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
        return ["frontend/package-lock.json: missing npm lock root"]
    if lock.get("lockfileVersion") != 3:
        problems.append("frontend/package-lock.json: npm lockfileVersion must be 3")

    for section in ("dependencies", "devDependencies"):
        expected = manifest.get(section, {})
        actual = packages[""].get(section, {})
        if expected != actual:
            problems.append(f"frontend/package-lock.json: root {section} disagrees with package.json")
        if isinstance(expected, dict):
            for package in expected:
                if f"node_modules/{package}" not in packages:
                    problems.append(f"frontend/package-lock.json: missing direct package {package}")

    for path, entry in packages.items():
        if not path:
            continue
        if not isinstance(entry, dict) or not entry.get("version"):
            problems.append(f"frontend/package-lock.json: {path} missing version")
            continue
        resolved = entry.get("resolved")
        if not isinstance(resolved, str) or not resolved.startswith(TRUSTED_NPM_REGISTRY):
            problems.append(f"frontend/package-lock.json: {path} has non-registry/missing URL")
        integrity = entry.get("integrity")
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            problems.append(f"frontend/package-lock.json: {path} missing SHA-512 integrity")
            continue
        try:
            digest = base64.b64decode(integrity.removeprefix("sha512-"), validate=True)
        except (binascii.Error, ValueError):
            digest = b""
        if len(digest) != 64:
            problems.append(f"frontend/package-lock.json: {path} malformed SHA-512 integrity")

    return problems



def expected_workspace_lock(root_manifest: dict, frontend_manifest: dict, frontend_lock: dict) -> dict:
    """Derive the root npm workspace lock from the canonical frontend lock.

    The canonical frontend/package-lock.json is retained for desktop builds;
    npm ci in a nested workspace resolves its workspace-root lock instead.
    Only the two virtual workspace entries are introduced. Registry artifacts
    and their integrity digests must match the canonical frontend lock exactly.
    """
    if root_manifest.get("private") is not True or root_manifest.get("workspaces") != ["frontend"]:
        raise ValueError("root package must declare private frontend workspace")
    if root_manifest.get("version") != frontend_manifest.get("version"):
        raise ValueError("root and frontend package versions differ")
    packages = frontend_lock.get("packages")
    if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
        raise ValueError("frontend npm lock lacks root package metadata")
    if packages[""].get("version") != frontend_manifest.get("version"):
        raise ValueError("frontend lock root version differs from package.json")
    if frontend_lock.get("lockfileVersion") != 3:
        raise ValueError("frontend npm lockfileVersion must be 3")
    if any(not path.startswith("node_modules/") for path in packages if path):
        raise ValueError("frontend lock contains unexpected non-registry workspace entries")
    return {
        "name": root_manifest["name"],
        "version": root_manifest["version"],
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {
                "name": root_manifest["name"],
                "version": root_manifest["version"],
                "workspaces": ["frontend"],
            },
            "frontend": packages[""],
            "node_modules/frontend": {"resolved": "frontend", "link": True},
            **{path: entry for path, entry in packages.items() if path},
        },
    }


def workspace_lock_issues(root: Path) -> list[str]:
    """Reject missing or stale root lock metadata before npm ci runs."""
    try:
        root_manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
        frontend_manifest = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
        frontend_lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
        root_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
        expected = expected_workspace_lock(root_manifest, frontend_manifest, frontend_lock)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        return [f"root workspace lock unavailable or invalid ({type(exc).__name__}): {exc}"]
    if root_lock != expected:
        return [
            "root package-lock.json disagrees with frontend/package-lock.json; "
            "run python scripts/sync_root_workspace_lock.py"
        ]
    return []


def check_locks(root: Path) -> list[str]:
    problems: list[str] = []
    versions: dict[str, dict[str, str]] = {}
    for filename in PYTHON_LOCKS:
        try:
            versions[filename], issues = parse_python_lock(root / filename)
        except (OSError, UnicodeError) as exc:
            problems.append(f"{filename}: unreadable lock ({type(exc).__name__})")
            continue
        problems.extend(issues)

    # These three locks must use the same versions wherever a package is shared.
    # This catches a partial remediation that accidentally leaves vulnerable
    # runtime pins inside the Windows/macOS dev or Linux packaged executable.
    for subset, superset in ((RUNTIME_LOCK, DEV_LOCK), (DEV_LOCK, LINUX_LOCK)):
        if subset not in versions or superset not in versions:
            continue
        for package, version in versions[subset].items():
            other = versions[superset].get(package)
            if other != version:
                problems.append(
                    f"Python lock drift: {package} is {version} in {subset}, "
                    f"{other or 'missing'} in {superset}"
                )

    try:
        problems.extend(npm_issues(root / "frontend/package.json", root / "frontend/package-lock.json"))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        problems.append(f"frontend: invalid npm lock or manifest ({type(exc).__name__})")
    problems.extend(workspace_lock_issues(root))
    return problems


def main() -> int:
    issues = check_locks(ROOT)
    if issues:
        print("Dependency lock structural audit FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        print("Do not fabricate hashes. Restore missing npm integrity from the trusted npm registry.")
        return 1
    print("Dependency locks: Python SHA-256 hashes, cross-lock parity and npm SHA-512 metadata verified.")
    print("Structural validation only. Run pip-audit, npm audit, and app tests separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
