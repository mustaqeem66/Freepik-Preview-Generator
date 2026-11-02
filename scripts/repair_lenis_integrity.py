#!/usr/bin/env python3
"""Restore the missing Lenis npm SRI value using the authoritative npm registry.

Default is offline, read-only inspection. Opt in to the network request and
lockfile write with --apply. Never generates or guesses a checksum.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = "node_modules/lenis"
VERSION = "1.3.27"
URL = "https://registry.npmjs.org/lenis/-/lenis-1.3.27.tgz"
REGISTRY = "https://registry.npmjs.org"
LOCK = ROOT / "frontend/package-lock.json"
MANIFEST = ROOT / "frontend/package.json"


def valid_sha512(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha512-"):
        return False
    try:
        digest = base64.b64decode(value[7:], validate=True)
    except (ValueError, binascii.Error):
        return False
    return len(digest) == 64


def _load_target(lock_path: Path, manifest_path: Path) -> tuple[dict, dict]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dependencies", {}).get("lenis") != VERSION:
        raise ValueError("Lenis direct dependency changed; stop and re-evaluate the exact version")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or not isinstance(packages.get(TARGET), dict):
        raise ValueError("Missing npm lock entry for lenis")
    pkg = packages[TARGET]
    if pkg.get("version") != VERSION or pkg.get("resolved") != URL:
        raise ValueError("Lenis lock version or registry URL does not match reviewed target")
    if packages.get("", {}).get("dependencies", {}).get("lenis") != VERSION:
        raise ValueError("npm lock root and package.json dependency versions differ")
    return lock, pkg


def official_integrity() -> str:
    command = [
        "npm", "view", f"lenis@{VERSION}", "dist.integrity", "--json",
        f"--registry={REGISTRY}",
    ]
    try:
        proc = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=45,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            "Cannot read the public npm registry securely. No lockfile changes were made."
        ) from exc
    try:
        value = json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError("npm registry returned non-JSON SRI data") from exc
    if not valid_sha512(value):
        raise RuntimeError("npm registry returned missing or malformed SHA-512 integrity")
    return value


def apply_integrity(lock_path: Path, manifest_path: Path, value: str) -> str:
    if not valid_sha512(value):
        raise ValueError("Refusing to write invalid SHA-512 integrity")
    lock, pkg = _load_target(lock_path, manifest_path)
    previous = pkg.get("integrity")
    if previous is not None and previous != value:
        raise ValueError("Refusing to replace a differing existing SRI; investigate first")
    if previous == value:
        return "unchanged"
    pkg["integrity"] = value
    # Update the one reviewed entry while retaining the lock's JSON ordering.
    # Atomic replacement prevents truncation if the process is interrupted.
    rendered = json.dumps(lock, indent=2, ensure_ascii=False) + "\n"
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=lock_path.parent,
            prefix=".package-lock-sri-", suffix=".tmp", delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, lock_path)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return "updated"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Fetch official SRI via npm view and patch the checked-in lockfile (network/write opt-in).",
    )
    args = parser.parse_args(argv)
    try:
        _, pkg = _load_target(LOCK, MANIFEST)
        if not args.apply:
            value = pkg.get("integrity")
            print(
                "Lenis SHA-512 integrity present (format valid)."
                if valid_sha512(value) else
                "Lenis SHA-512 integrity missing/invalid. Run --apply using a trusted npm connection."
            )
            return 0 if valid_sha512(value) else 1
        value = official_integrity()
        outcome = apply_integrity(LOCK, MANIFEST, value)
        print(f"Lenis lock integrity {outcome}; run npm ci, tests and the offline lock gate.")
        return 0
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
