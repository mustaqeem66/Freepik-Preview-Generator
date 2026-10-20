"""Installer script regressions (P0-4).

``install.sh`` previously did ``sha256sum ... | awk ... || shasum ... | awk``.
Because ``awk`` succeeds even when ``sha256sum`` is missing, the ``||`` fallback
never ran on macOS and the computed hash was empty. The helper is now resolved
once via ``command -v``.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INSTALL_SH = PROJECT_ROOT / "install.sh"

pytestmark = [
    pytest.mark.core,
    pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable"),
]

BASH = shutil.which("bash") or "bash"
# Windows' "bash.exe" is usually the WSL launcher, which rewrites/mangles
# Windows paths. Syntax/hash execution is covered on the Linux and macOS legs.
bash_exec = pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="POSIX bash with native path handling unavailable",
)


def _install_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


@bash_exec
def test_install_sh_is_valid_bash():
    result = subprocess.run(
        [BASH, "-n", str(INSTALL_SH)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_checksum_fallback_is_not_masked_by_awk():
    text = _install_text()
    assert "hash_sha256()" in text
    assert re.search(r"sha256sum\s+\"\$file\"[^\n]*\|\|[^\n]*shasum", text) is None
    assert "command -v sha256sum" in text
    assert "command -v shasum" in text
    assert "No SHA-256 tool available" in text


def _extract_hash_function(text: str) -> str:
    match = re.search(r"^hash_sha256\(\) \{.*?^\}", text, re.MULTILINE | re.DOTALL)
    assert match, "hash_sha256() helper not found in install.sh"
    return match.group(0)


@bash_exec
@pytest.mark.skipif(shutil.which("awk") is None, reason="awk unavailable")
def test_hash_sha256_uses_shasum_when_sha256sum_absent(tmp_path):
    shasum = shutil.which("shasum")
    openssl = shutil.which("openssl")
    if shasum is None and openssl is None:
        pytest.skip("neither shasum nor openssl available")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for tool in (shasum, openssl, shutil.which("awk")):
        if tool:
            target = fake_bin / Path(tool).name
            target.symlink_to(tool)

    payload = tmp_path / "artifact.bin"
    payload.write_bytes(b"previewgen-installer-payload")
    expected = hashlib.sha256(payload.read_bytes()).hexdigest()

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "set -euo pipefail\n"
        + _extract_hash_function(_install_text())
        + '\nhash_sha256 "$1"\n',
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["PATH"] = str(fake_bin)
    result = subprocess.run(
        [BASH, str(harness), str(payload)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_powershell_installer_verifies_checksums_fail_closed():
    text = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
    # The setup asset and its checksum are mandatory: a release without either
    # must abort rather than fall back to an unverified install.
    assert "PreviewGen-Setup.exe" in text
    assert "refusing an unverified install" in text
    assert "no valid hash for PreviewGen-Setup.exe" in text
    assert "SHA-256 verification failed" in text
    assert "Start-Process" in text
    # Uninstall registration belongs to the Inno Setup wizard, not this script.
    assert "uninstall.bat" not in text


def test_install_sh_creates_shortcuts_and_uninstaller():
    text = _install_text()
    # Quarantine is a security decision owned by the user, not a build
    # convenience: the installer must never strip it silently.
    assert "xattr" not in text
    assert "right-click > Open" in text
    assert "previewgen-uninstall" in text
    assert "Desktop/previewgen.desktop" in text
    assert "Desktop/$APP_NAME.app" in text
    assert "PREVIEWGEN_NO_LAUNCH" in text


def test_bash_installer_verifies_checksums_fail_closed():
    text = _install_text()
    # Mirrors install.ps1: a release with no manifest, no downloadable manifest,
    # or no matching hash must abort instead of installing an unverified binary.
    assert "verify_checksum" in text
    assert "publishes no SHA256SUMS.txt" in text
    assert "Could not download SHA256SUMS.txt" in text
    assert "No SHA-256 entry for" in text
    assert "Checksum verification failed" in text
