"""Packaged Linux WebKitGTK bundle verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFIER = PROJECT_ROOT / "scripts" / "verify_linux_webkit_bundle.py"


def _make_onedir(root: Path, *, include_injected_bundle: bool) -> Path:
    artifact = root / "PreviewGen"
    artifact.mkdir()
    (artifact / "libwebkit2gtk-4.1.so.0").write_bytes(b"frozen webkit library")
    if include_injected_bundle:
        bundle_dir = artifact / "webkit_injected_bundle"
        bundle_dir.mkdir()
        (bundle_dir / "libwebkit2gtkinjectedbundle.so").write_bytes(b"matching injected bundle")
    return artifact


def test_verifier_rejects_missing_injected_bundle(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path, include_injected_bundle=False)

    result = subprocess.run(
        [sys.executable, str(VERIFIER), str(artifact)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "libwebkit2gtkinjectedbundle.so" in result.stderr


def test_verifier_accepts_present_matching_injected_bundle(tmp_path: Path) -> None:
    artifact = _make_onedir(tmp_path, include_injected_bundle=True)

    result = subprocess.run(
        [sys.executable, str(VERIFIER), str(artifact)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "matching injected bundle" in result.stdout
