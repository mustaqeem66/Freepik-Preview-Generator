"""Packaged Linux WebKitGTK bundle verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFIER = PROJECT_ROOT / "scripts" / "verify_linux_webkit_bundle.py"
MANIFEST_NAME = "webkit_manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(bundle_dir: Path, library: Path, bundle: Path) -> Path:
    manifest = {
        "schema_version": 1,
        "api_version": "4.1",
        "package_name": "libwebkit2gtk-4.1-0",
        "package_version": "1:2.50.4-1",
        "library_filename": library.name,
        "library_sha256": _sha256(library),
        "injected_bundle_filename": bundle.name,
        "injected_bundle_sha256": _sha256(bundle),
        "injected_bundle_needed": ["libwebkit2gtk-4.1.so.0"],
    }
    manifest_path = bundle_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _make_onedir(root: Path, *, include_injected_bundle: bool = True) -> Path:
    artifact = root / "PreviewGen"
    artifact.mkdir(parents=True)
    library = artifact / "libwebkit2gtk-4.1.so.0"
    library.write_bytes(b"frozen webkit library")
    if include_injected_bundle:
        bundle_dir = artifact / "webkit_injected_bundle"
        bundle_dir.mkdir()
        bundle = bundle_dir / "libwebkit2gtkinjectedbundle.so"
        bundle.write_bytes(b"matching injected bundle")
        _write_manifest(bundle_dir, library, bundle)
    return artifact


def _run_verifier(artifact: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(artifact)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_verifier_rejects_missing_injected_bundle(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path, include_injected_bundle=False)

    result = _run_verifier(artifact)

    assert result.returncode != 0
    assert "libwebkit2gtkinjectedbundle.so" in result.stderr


def test_verifier_rejects_missing_provenance_manifest(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path)
    (artifact / "webkit_injected_bundle" / MANIFEST_NAME).unlink()

    result = _run_verifier(artifact)

    assert result.returncode != 0
    assert MANIFEST_NAME in result.stderr


def test_verifier_rejects_library_that_does_not_match_manifest(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path)
    (artifact / "libwebkit2gtk-4.1.so.0").write_bytes(b"different webkit library")

    result = _run_verifier(artifact)

    assert result.returncode != 0
    assert "library checksum" in result.stderr


def test_verifier_rejects_injected_bundle_that_does_not_match_manifest(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path)
    (artifact / "webkit_injected_bundle" / "libwebkit2gtkinjectedbundle.so").write_bytes(b"different bundle")

    result = _run_verifier(artifact)

    assert result.returncode != 0
    assert "injected bundle checksum" in result.stderr


def test_verifier_rejects_package_name_that_contradicts_the_api_version(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path)
    manifest_path = artifact / "webkit_injected_bundle" / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package_name"] = "libwebkit2gtk-4.0-0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _run_verifier(artifact)

    assert result.returncode != 0
    assert "package name" in result.stderr


def test_verifier_accepts_present_matching_injected_bundle(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path)

    result = _run_verifier(artifact)

    assert result.returncode == 0, result.stderr
    assert "matching injected bundle" in result.stdout


def _make_extracting_appimage(source: Path, destination: Path, *, exit_code: int = 0) -> Path:
    script = f"""#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path
if {exit_code!r}:
    raise SystemExit({exit_code!r})
source = Path({str(source)!r})
root = Path("squashfs-root")
shutil.copytree(source, root / "usr" / "bin" / "_internal")
"""
    destination.write_text(script, encoding="utf-8")
    destination.chmod(0o755)
    return destination


@pytest.mark.skipif(sys.platform == "win32", reason="AppImage executables are Linux-only")
def test_verifier_accepts_appimage_after_extraction(tmp_path: Path) -> None:
    source = _make_onedir(tmp_path / "source")
    artifact = _make_extracting_appimage(source, tmp_path / "PreviewGen-Linux.AppImage")

    result = _run_verifier(artifact)

    assert result.returncode == 0, result.stderr
    assert "matching injected bundle" in result.stdout


@pytest.mark.skipif(sys.platform == "win32", reason="AppImage executables are Linux-only")
def test_verifier_rejects_failed_appimage_extraction(tmp_path: Path) -> None:
    artifact = _make_extracting_appimage(tmp_path, tmp_path / "broken.AppImage", exit_code=7)

    result = _run_verifier(artifact)

    assert result.returncode != 0
    assert "Could not extract AppImage" in result.stderr
