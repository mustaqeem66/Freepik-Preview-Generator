#!/usr/bin/env python3
"""Rebuild the root npm workspace lock from the canonical frontend lock.

This command is offline and never contacts registries or manufactures hashes.
Run it after updating frontend/package-lock.json with npm, then run
scripts/verify_dependency_locks.py and native/frontend npm ci gates.
"""
from __future__ import annotations

import json
from pathlib import Path

from verify_dependency_locks import expected_workspace_lock

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    root = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    data = expected_workspace_lock(root, frontend, lock)
    (ROOT / "package-lock.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print("Regenerated root package-lock.json from frontend canonical lock (offline).")


if __name__ == "__main__":
    main()
