"""No-network tests for dependency lock parity and checksum metadata."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from scripts.verify_dependency_locks import check_locks, expected_workspace_lock

pytestmark = pytest.mark.core


def fixture_tree(tmp_path: Path) -> Path:
    runtime = "example==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n"
    dev = runtime + "pytest==9.0 \\\n    --hash=sha256:" + "b" * 64 + "\n"
    linux = dev + "pygobject==3.50.2 \\\n    --hash=sha256:" + "c" * 64 + "\n"
    for name, content in (
        ("requirements-lock.txt", runtime),
        ("requirements-dev-lock.txt", dev),
        ("requirements-linux-gui-lock.txt", linux),
    ):
        (tmp_path / name).write_text(content, encoding="utf-8")

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    deps = {"lenis": "1.3.27"}
    frontend_manifest = {
        "name": "frontend", "version": "1.0.0",
        "dependencies": deps, "devDependencies": {},
    }
    frontend_lock = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "frontend", "version": "1.0.0",
                 "dependencies": deps, "devDependencies": {}},
            "node_modules/lenis": {
                "version": "1.3.27",
                "resolved": "https://registry.npmjs.org/lenis/-/lenis-1.3.27.tgz",
                "integrity": "sha512-" + base64.b64encode(bytes(64)).decode("ascii"),
            },
        },
    }
    root_manifest = {
        "name": "previewgen-cloud-preview", "version": "1.0.0",
        "private": True, "workspaces": ["frontend"],
    }
    (frontend / "package.json").write_text(json.dumps(frontend_manifest), encoding="utf-8")
    (frontend / "package-lock.json").write_text(json.dumps(frontend_lock), encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps(root_manifest), encoding="utf-8")
    root_lock = expected_workspace_lock(root_manifest, frontend_manifest, frontend_lock)
    (tmp_path / "package-lock.json").write_text(json.dumps(root_lock), encoding="utf-8")
    return tmp_path


def test_valid_lock_graph_passes(tmp_path: Path):
    assert check_locks(fixture_tree(tmp_path)) == []


def test_missing_npm_integrity_is_security_failure(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "frontend/package-lock.json"
    data = json.loads(path.read_text())
    del data["packages"]["node_modules/lenis"]["integrity"]
    path.write_text(json.dumps(data))
    assert any("lenis missing SHA-512 integrity" in error for error in check_locks(root))


def test_malformed_npm_integrity_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "frontend/package-lock.json"
    data = json.loads(path.read_text())
    data["packages"]["node_modules/lenis"]["integrity"] = "sha512-not-64-bytes"
    path.write_text(json.dumps(data))
    assert any("lenis malformed SHA-512" in error for error in check_locks(root))


def test_python_cross_lock_version_drift_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "requirements-linux-gui-lock.txt"
    path.write_text(path.read_text().replace("example==1.0", "example==0.8"))
    assert any("example is 1.0" in error for error in check_locks(root))


def test_python_missing_hash_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "requirements-lock.txt"
    path.write_text("example==1.0\n")
    assert any("lacks SHA-256" in error for error in check_locks(root))


def test_npm_manifest_lock_drift_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "frontend/package.json"
    data = json.loads(path.read_text())
    data["dependencies"]["lenis"] = "1.3.26"
    path.write_text(json.dumps(data))
    assert any("disagrees with package.json" in error for error in check_locks(root))


def test_non_registry_package_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "frontend/package-lock.json"
    data = json.loads(path.read_text())
    data["packages"]["node_modules/lenis"]["resolved"] = "https://example.invalid/lenis.tgz"
    path.write_text(json.dumps(data))
    assert any("lenis has non-registry" in error for error in check_locks(root))


def test_root_workspace_lock_missing_is_release_failure(tmp_path: Path):
    root = fixture_tree(tmp_path)
    (root / "package-lock.json").unlink()
    assert any("root workspace lock unavailable" in issue for issue in check_locks(root))


def test_workspace_lock_cannot_silently_drift_from_frontend_lock(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "package-lock.json"
    lock = json.loads(path.read_text())
    del lock["packages"]["node_modules/lenis"]["integrity"]
    path.write_text(json.dumps(lock))
    assert any("root package-lock.json disagrees" in issue for issue in check_locks(root))


def test_workspace_root_link_is_not_treated_as_unhashed_registry_artifact(tmp_path: Path):
    root = fixture_tree(tmp_path)
    assert check_locks(root) == []
