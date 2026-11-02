"""Offline tests for safe, opt-in Lenis integrity repair."""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import repair_lenis_integrity as repair

pytestmark = pytest.mark.core
GOOD = "sha512-" + base64.b64encode(bytes(range(64))).decode("ascii")
OTHER = "sha512-" + base64.b64encode(bytes(reversed(range(64)))).decode("ascii")


def fixture_files(tmp_path: Path) -> tuple[Path, Path]:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    manifest = frontend / "package.json"
    lock = frontend / "package-lock.json"
    manifest.write_text(json.dumps({"dependencies": {"lenis": repair.VERSION}}))
    lock.write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"dependencies": {"lenis": repair.VERSION}},
            repair.TARGET: {"version": repair.VERSION, "resolved": repair.URL},
        },
    }))
    return lock, manifest


def test_offline_status_detects_missing_integrity(tmp_path: Path):
    lock, manifest = fixture_files(tmp_path)
    _, entry = repair._load_target(lock, manifest)
    assert not repair.valid_sha512(entry.get("integrity"))


def test_apply_repairs_only_target_and_is_idempotent(tmp_path: Path):
    lock, manifest = fixture_files(tmp_path)
    old = json.loads(lock.read_text())
    assert repair.apply_integrity(lock, manifest, GOOD) == "updated"
    new = json.loads(lock.read_text())
    assert new["packages"][repair.TARGET]["integrity"] == GOOD
    del new["packages"][repair.TARGET]["integrity"]
    assert old == new
    assert repair.apply_integrity(lock, manifest, GOOD) == "unchanged"


def test_conflicting_hash_refused_without_modification(tmp_path: Path):
    lock, manifest = fixture_files(tmp_path)
    assert repair.apply_integrity(lock, manifest, GOOD) == "updated"
    original = lock.read_bytes()
    with pytest.raises(ValueError, match="differing existing"):
        repair.apply_integrity(lock, manifest, OTHER)
    assert lock.read_bytes() == original


def test_invalid_hash_refused(tmp_path: Path):
    lock, manifest = fixture_files(tmp_path)
    original = lock.read_bytes()
    with pytest.raises(ValueError, match="invalid SHA-512"):
        repair.apply_integrity(lock, manifest, "sha512-not-valid")
    assert lock.read_bytes() == original


def test_registry_or_version_mismatch_refused(tmp_path: Path):
    lock, manifest = fixture_files(tmp_path)
    data = json.loads(lock.read_text())
    data["packages"][repair.TARGET]["resolved"] = "https://example.invalid/lenis.tgz"
    lock.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="registry URL"):
        repair.apply_integrity(lock, manifest, GOOD)


def test_official_npm_view_uses_exact_version_and_registry(monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(repair.shutil, "which", lambda name: r"C:\\Program Files\\nodejs\\npm.cmd")

    def fake_run(command, *, check, capture_output, text, timeout):
        calls.append(command)
        assert check and capture_output and text and timeout == 45
        return SimpleNamespace(stdout=json.dumps(GOOD))

    monkeypatch.setattr(repair.subprocess, "run", fake_run)
    assert repair.official_integrity() == GOOD
    assert calls[0] == [
        r"C:\\Program Files\\nodejs\\npm.cmd", "view", "lenis@1.3.27", "dist.integrity", "--json",
        "--registry=https://registry.npmjs.org",
    ]


def test_npm_registry_failure_is_not_hidden(monkeypatch):
    monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/npm")

    def failed(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "npm view")
    monkeypatch.setattr(repair.subprocess, "run", failed)
    with pytest.raises(RuntimeError, match="No lockfile changes"):
        repair.official_integrity()


def test_missing_npm_cli_fails_without_spawning_any_process(monkeypatch):
    monkeypatch.setattr(repair.shutil, "which", lambda name: None)

    def never_spawn(*_args, **_kwargs):
        raise AssertionError("must not invoke subprocess without npm CLI")

    monkeypatch.setattr(repair.subprocess, "run", never_spawn)
    with pytest.raises(RuntimeError, match="npm CLI not found on PATH"):
        repair.official_integrity()
