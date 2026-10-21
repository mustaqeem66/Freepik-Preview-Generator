#!/usr/bin/env python3
"""Run PreviewGen source-level release checks locally without GitHub Actions.

Examples, from the repository root:
    python scripts/check_release_locally.py
    python scripts/check_release_locally.py --mode full
    python scripts/check_release_locally.py --frontend-only
    python scripts/check_release_locally.py --npm-ci

By default this command never installs packages or uploads results.
It records only command labels, argv, status and duration in a local JSON file.
Native Windows/macOS/Linux GUI and packaging tests remain manual release gates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Check:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    require_bundle: bool = False


def plan_checks(
    root: Path,
    *,
    mode: str = "core",
    backend: bool = True,
    frontend: bool = True,
    npm_ci: bool = False,
    python: str | None = None,
    npm: str = "npm",
) -> list[Check]:
    """Create an inspectable ordered plan; no commands are executed here."""
    if mode not in {"core", "full"}:
        raise ValueError("mode must be core or full")
    if not backend and not frontend:
        raise ValueError("Select at least one test target")
    py = python or sys.executable
    frontend_dir = root / "frontend"
    checks: list[Check] = []

    if backend:
        checks.append(Check("backend-ruff", (py, "-m", "ruff", "check", "."), root))
        if mode == "core":
            checks.append(Check("backend-core-tests", (py, "-m", "pytest", "tests/unit", "-m", "core", "-q"), root))
        else:
            checks.append(Check("backend-all-tests", (py, "-m", "pytest", "tests", "-q"), root))
            checks.append(Check("renderer-capabilities", (py, "scripts/verify_environment.py"), root))
            checks.append(Check("renderer-format-inventory", (py, "scripts/audit_renderer_matrix.py"), root))

    if frontend:
        if npm_ci:
            checks.append(Check("frontend-install", (npm, "ci"), frontend_dir))
        checks.extend((
            Check("frontend-typecheck", (npm, "run", "typecheck"), frontend_dir),
            Check("frontend-unit-tests", (npm, "test"), frontend_dir),
            Check("frontend-production-build", (npm, "run", "build"), frontend_dir),
            Check("frontend-bundle-csp", (py, "-m", "pytest", "tests/frontend/test_bundle.py", "-q"),
                  root, require_bundle=True),
            Check("frontend-studio-design", (py, "scripts/verify_studio_bundle.py"), root),
        ))

    return checks


def run_checks(
    checks: list[Check], *, root: Path, report: Path, fail_fast: bool = False
) -> int:
    """Print subprocess output live and write a minimal machine-readable record."""
    report.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    started = dt.datetime.now(dt.UTC).isoformat()

    if (
        any(check.name.startswith("frontend-") for check in checks)
        and not (root / "frontend" / "node_modules").is_dir()
        and not any(check.name == "frontend-install" for check in checks)
    ):
        print(
                "NOTICE: frontend/node_modules missing. Run 'cd frontend && npm ci' "
                "or add --npm-ci to permit local dependency installation.",
                flush=True,
            )

    try:
        for check in checks:
            print(f"\n==> {check.name}: {' '.join(check.argv)}", flush=True)
            started_clock = time.monotonic()
            env: dict[str, str] | None = None
            if check.require_bundle:
                import os

                env = dict(os.environ)
                env["PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE"] = "1"
            try:
                process = subprocess.run(
                    list(check.argv), cwd=check.cwd, env=env, check=False,
                )
                code = process.returncode
            except OSError as exc:
                print(f"ERROR: unable to launch {check.name}: {exc}", flush=True)
                code = 127
            duration = round(time.monotonic() - started_clock, 2)
            results.append({
                # A virtualenv/npm executable may live under C:\\Users\\name or
                # /home/name. Keep local usernames out of sharable QA reports.
                "name": check.name, "argv": [Path(check.argv[0]).name, *check.argv[1:]],
                "status": "pass" if code == 0 else "fail",
                "exitCode": code, "durationSeconds": duration,
            })
            print(f"<== {check.name}: {'PASS' if code == 0 else 'FAIL'} ({duration}s)", flush=True)
            if code != 0 and fail_fast:
                break
    finally:
        succeeded = sum(item["status"] == "pass" for item in results)
        payload: dict[str, Any] = {
            "schemaVersion": 1, "startedAtUtc": started,
            "completedAtUtc": dt.datetime.now(dt.UTC).isoformat(),
            "host": {"system": platform.system(), "python": platform.python_version()},
            "summary": {"passed": succeeded, "failed": len(results) - succeeded,
                        "planned": len(checks), "completed": len(results)},
            "results": results,
            "note": (
                "Source-level checks only. No real native WebView, Windows idle-hang, "
                "installer, signing, or platform release gate was performed."
            ),
        }
        report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nLocal check report: {report}", flush=True)

    return 0 if len(results) == len(checks) and all(item["exitCode"] == 0 for item in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("core", "full"), default="core")
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--backend-only", action="store_true")
    targets.add_argument("--frontend-only", action="store_true")
    parser.add_argument(
        "--npm-ci", action="store_true",
        help="Opt into npm ci, which may access the network; default is no installation.",
    )
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--report", type=Path, default=Path("local-check-report.json"),
        help="Local JSON results file (default: local-check-report.json in repo root)",
    )
    args = parser.parse_args(argv)
    if args.npm_ci and args.backend_only:
        parser.error("--npm-ci cannot be combined with --backend-only")
    npm = shutil.which("npm") or "npm"
    checks = plan_checks(
        ROOT, mode=args.mode, backend=not args.frontend_only,
        frontend=not args.backend_only, npm_ci=args.npm_ci,
        npm=npm,
    )
    report = args.report if args.report.is_absolute() else ROOT / args.report
    return run_checks(checks, root=ROOT, report=report, fail_fast=args.fail_fast)


if __name__ == "__main__":
    raise SystemExit(main())
