"""No-network, platform-independent checks for the local QA command planner."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_release_locally as release

pytestmark = pytest.mark.core


def test_core_plan_builds_frontend_before_bundle_csp(tmp_path: Path) -> None:
    checks = release.plan_checks(tmp_path, python="py", npm="npm")
    names = [check.name for check in checks]
    assert names == [
        "backend-ruff", "backend-pyrefly", "backend-core-tests", "frontend-typecheck",
        "frontend-unit-tests", "frontend-production-build", "frontend-bundle-csp",
        "frontend-studio-design",
    ]
    assert checks[-2].require_bundle is True
    assert checks[-1].name == "frontend-studio-design"
    assert "frontend-install" not in names


def test_full_release_plan_includes_capability_gate_and_all_tests(tmp_path: Path) -> None:
    checks = release.plan_checks(tmp_path, mode="full", python="py")
    names = [check.name for check in checks]
    assert "backend-all-tests" in names
    assert "renderer-capabilities" in names
    assert "renderer-format-inventory" in names
    assert "backend-core-tests" not in names


def test_frontend_dependency_install_is_opt_in(tmp_path: Path) -> None:
    checks = release.plan_checks(
        tmp_path, backend=False, frontend=True, npm_ci=True,
        python="py", npm="npm.cmd",
    )
    assert checks[0].name == "frontend-install"
    assert checks[0].argv == ("npm.cmd", "ci")
    assert not any(check.name.startswith("backend-") for check in checks)


def test_bundle_csp_check_requires_production_bundle_environment(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    calls: list[dict] = []

    def pretend_subprocess(argv, *, cwd, env, check):
        calls.append({"argv": argv, "cwd": cwd, "env": env, "check": check})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release.subprocess, "run", pretend_subprocess)
    report = tmp_path / "checks.json"
    checks = release.plan_checks(tmp_path, frontend=True, backend=False, python="python", npm="npm")
    assert release.run_checks(checks, root=tmp_path, report=report) == 0
    assert calls[-2]["env"]["PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE"] == "1"
    assert calls[-1]["env"] is None
    assert calls[0]["env"] is None
    data = json.loads(report.read_text())
    assert data["summary"]["passed"] == 5
    assert data["summary"]["failed"] == 0
    assert all(entry["status"] == "pass" for entry in data["results"])
    assert all("/" not in entry["argv"][0] and "\\" not in entry["argv"][0]
               for entry in data["results"])
    assert "No real native WebView" in data["note"]


def test_hoisted_workspace_install_does_not_emit_false_dependency_notice(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # npm ci inside a frontend workspace can hoist packages into root/node_modules.
    (tmp_path / "node_modules").mkdir()
    monkeypatch.setattr(
        release.subprocess, "run",
        lambda *_a, **_kw: SimpleNamespace(returncode=0),
    )
    checks = release.plan_checks(tmp_path, frontend=True, backend=False, python="python")
    assert release.frontend_deps_available(tmp_path)
    assert release.run_checks(checks, root=tmp_path, report=tmp_path / "release.json") == 0
    assert "NOTICE: npm dependencies missing" not in capsys.readouterr().out


def test_missing_workspace_dependencies_still_emits_install_notice(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        release.subprocess, "run",
        lambda *_a, **_kw: SimpleNamespace(returncode=0),
    )
    checks = release.plan_checks(tmp_path, frontend=True, backend=False, python="python")
    assert not release.frontend_deps_available(tmp_path)
    assert release.run_checks(checks, root=tmp_path, report=tmp_path / "release.json") == 0
    assert "NOTICE: npm dependencies missing" in capsys.readouterr().out


def test_failure_returns_nonzero_and_records_failure_without_hiding_it(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    calls = 0

    def pretend_subprocess(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(returncode=2 if calls == 2 else 0)

    monkeypatch.setattr(release.subprocess, "run", pretend_subprocess)
    report = tmp_path / "failed.json"
    checks = release.plan_checks(tmp_path, backend=False, python="py")
    assert release.run_checks(checks, root=tmp_path, report=report) == 1
    data = json.loads(report.read_text())
    assert data["summary"]["failed"] == 1
    assert data["summary"]["completed"] == len(checks)
    assert data["results"][1]["exitCode"] == 2


def test_fail_fast_stops_remaining_checks_but_reports_unexecuted_count(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(release.subprocess, "run", lambda *_a, **_kw: SimpleNamespace(returncode=4))
    checks = release.plan_checks(tmp_path, backend=True, frontend=False)
    report = tmp_path / "fast.json"
    assert release.run_checks(checks, root=tmp_path, report=report, fail_fast=True) == 1
    data = json.loads(report.read_text())
    assert data["summary"]["completed"] == 1
    assert data["summary"]["planned"] == len(checks)


def test_plan_rejects_empty_selection(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        release.plan_checks(tmp_path, backend=False, frontend=False)


def test_security_audit_is_explicit_opt_in_and_scans_all_lockfiles(tmp_path: Path) -> None:
    normal = release.plan_checks(tmp_path, python="py", npm="npm")
    assert not any(check.name.startswith("security-") for check in normal)

    checks = release.plan_checks(tmp_path, security_audit=True, python="py", npm="npm")
    audits = [check for check in checks if check.name.startswith("security-")]
    assert len(audits) == 5
    assert [check.name for check in audits] == [
        "security-lock-integrity",
        "security-pip-audit-requirements-lock.txt",
        "security-pip-audit-requirements-dev-lock.txt",
        "security-pip-audit-requirements-linux-gui-lock.txt",
        "security-npm-audit",
    ]
    assert audits[0].argv == ("py", "scripts/verify_dependency_locks.py")
    assert all(check.argv[1:4] == ("-m", "pip_audit", "--require-hashes") for check in audits[1:4])
    assert all(check.cwd == tmp_path for check in audits[:4])
    assert audits[-1].argv == (
        "npm", "audit", "--package-lock-only", "--audit-level=low", "--include=dev"
    )
    assert audits[-1].cwd == tmp_path / "frontend"


def test_security_audit_respects_target_selection(tmp_path: Path) -> None:
    backend = release.plan_checks(tmp_path, frontend=False, security_audit=True, python="py")
    assert sum(check.name.startswith("security-pip-audit") for check in backend) == 3
    assert all(check.name != "security-npm-audit" for check in backend)

    frontend = release.plan_checks(tmp_path, backend=False, security_audit=True, npm="npm")
    assert sum(check.name == "security-npm-audit" for check in frontend) == 1
    assert all(not check.name.startswith("security-pip-audit") for check in frontend)
    assert any(check.name == "security-lock-integrity" for check in frontend)


def test_vulnerability_audit_failure_blocks_local_release(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    def pretend_subprocess(argv, *, cwd, env, check):
        return SimpleNamespace(returncode=1 if "audit" in argv or "pip_audit" in argv else 0)

    monkeypatch.setattr(release.subprocess, "run", pretend_subprocess)
    checks = release.plan_checks(tmp_path, frontend=False, security_audit=True, python="py")
    report = tmp_path / "audit-fail.json"
    assert release.run_checks(checks, root=tmp_path, report=report) == 1
    data = json.loads(report.read_text())
    assert data["summary"]["failed"] == 3
    assert data["summary"]["completed"] == len(checks)
