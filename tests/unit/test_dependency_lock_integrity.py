"""No-network tests for dependency lock parity and checksum metadata."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from scripts.verify_dependency_locks import check_locks

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
        "name": "frontend",
        "version": "1.0.0",
        "dependencies": deps,
        "devDependencies": {},
    }
    frontend_lock = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "frontend", "version": "1.0.0", "dependencies": deps, "devDependencies": {}},
            "node_modules/lenis": {
                "version": "1.3.27",
                "resolved": "https://registry.npmjs.org/lenis/-/lenis-1.3.27.tgz",
                "integrity": "sha512-" + base64.b64encode(bytes(64)).decode("ascii"),
            },
        },
    }
    (frontend / "package.json").write_text(json.dumps(frontend_manifest), encoding="utf-8")
    (frontend / "package-lock.json").write_text(json.dumps(frontend_lock), encoding="utf-8")
    # The root package is a script-only entrypoint. It must not declare npm
    # workspaces, because npm would then resolve a workspace-root lock and
    # ignore frontend/package-lock.json entirely.
    root_manifest = {
        "name": "previewgen-cloud-preview",
        "version": "1.0.0",
        "private": True,
        "scripts": {
            "dev": "npm --prefix frontend run dev",
            "build": "npm --prefix frontend run build",
            "test": "npm --prefix frontend test",
            "typecheck": "npm --prefix frontend run typecheck",
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(root_manifest), encoding="utf-8")
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


def test_frontend_lock_missing_is_release_failure(tmp_path: Path):
    root = fixture_tree(tmp_path)
    (root / "frontend/package-lock.json").unlink()
    assert any("invalid npm lock or manifest" in issue for issue in check_locks(root))


def test_root_workspace_declaration_is_rejected(tmp_path: Path):
    # npm workspaces make npm resolve a workspace-root lock instead of the
    # canonical frontend lock, which silently breaks dependency update PRs.
    root = fixture_tree(tmp_path)
    path = root / "package.json"
    data = json.loads(path.read_text())
    data["workspaces"] = ["frontend"]
    path.write_text(json.dumps(data))
    assert any("must not declare npm workspaces" in issue for issue in check_locks(root))


def test_root_lock_file_is_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    (root / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3}), encoding="utf-8")
    assert any("must not exist" in issue for issue in check_locks(root))


def test_root_missing_script_is_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "package.json"
    data = json.loads(path.read_text())
    del data["scripts"]["build"]
    path.write_text(json.dumps(data))
    assert any("missing the 'build' script" in issue for issue in check_locks(root))


def test_frontend_lock_is_the_only_npm_lock(tmp_path: Path):
    # The repository must not carry a second npm lock that npm would prefer.
    root = fixture_tree(tmp_path)
    assert not (root / "package-lock.json").exists()
    assert (root / "frontend/package-lock.json").is_file()
    assert check_locks(root) == []


def test_root_script_must_delegate_to_the_frontend_lock(tmp_path: Path):
    # A root script that runs npm from the repository root would resolve a
    # root lock that does not exist, and `npm install` would bypass the
    # exact-lock reinstall that `npm ci` guarantees.
    root = fixture_tree(tmp_path)
    path = root / "package.json"
    data = json.loads(path.read_text())
    data["scripts"]["build"] = "cd frontend && npm install"
    path.write_text(json.dumps(data))
    assert any("must start with 'npm --prefix frontend '" in issue for issue in check_locks(root))


def test_root_script_running_npm_at_the_repository_root_is_rejected(tmp_path: Path):
    root = fixture_tree(tmp_path)
    path = root / "package.json"
    data = json.loads(path.read_text())
    data["scripts"]["test"] = "npm test"
    path.write_text(json.dumps(data))
    assert any("must start with 'npm --prefix frontend '" in issue for issue in check_locks(root))


def test_pillow_ceiling_preserves_psd_tools_imagemath_compatibility() -> None:
    """Pillow 13 removed the ImageMath API used by the PSD renderer."""
    root = Path(__file__).resolve().parent.parent.parent
    requirements = (root / "requirements.in").read_text(encoding="utf-8")

    assert "Pillow>=10.0.0,<13" in requirements


def test_non_object_root_manifest_is_reported_not_raised(tmp_path: Path):
    # A syntactically valid root file that is not a JSON object must produce a
    # clear diagnostic instead of an AttributeError traceback.
    root = fixture_tree(tmp_path)
    (root / "package.json").write_text("[]", encoding="utf-8")
    issues = check_locks(root)
    assert any("must contain a JSON object" in issue for issue in issues)
