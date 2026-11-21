"""Windows uninstall contract (NEW-6).

Windows uninstalling is performed by Inno Setup's generated ``unins000.exe``,
not by a hand-written batch file. The uninstaller must be registered in the
Start Menu, must be reachable through the stable AppId so an upgrade replaces
the existing installation instead of installing beside it, and must be able to
unlock its own files — Inno Setup copies the uninstaller to a temporary
directory before running it, which is what lets it delete the install
directory.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INSTALLER_ISS = PROJECT_ROOT / "installer.iss"

pytestmark = pytest.mark.core


@pytest.fixture(scope="module")
def installer_text() -> str:
    return INSTALLER_ISS.read_text(encoding="utf-8")


def _section(text: str, name: str) -> str:
    match = re.search(
        rf"^\[{re.escape(name)}\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match, f"section [{name}] is missing from installer.iss"
    return match.group(1)


def test_the_installer_registers_a_start_menu_uninstaller(installer_text):
    icons = _section(installer_text, "Icons")
    assert 'Name: "{group}\\Uninstall {#MyAppName}"' in icons
    assert 'Filename: "{uninstallexe}"' in icons


def test_the_installer_uses_a_stable_app_id_for_upgrade_and_uninstall(installer_text):
    setup = _section(installer_text, "Setup")
    app_id = re.search(r"^AppId=(\{.*\})$", setup, re.MULTILINE)
    assert app_id, "AppId must be declared so upgrades replace the install"
    # The AppId is written with doubled braces so Inno emits a literal GUID.
    guid = app_id.group(1).replace("{{", "{").replace("}}", "}")
    assert re.fullmatch(r"\{[0-9A-F-]{36}\}", guid), f"malformed AppId: {guid}"


def test_the_installer_uninstalls_without_elevation(installer_text):
    setup = _section(installer_text, "Setup")
    assert "PrivilegesRequired=lowest" in setup
    assert "DefaultDirName={localappdata}\\Programs\\{#MyAppName}" in setup


def test_the_uninstaller_is_not_shadowed_by_a_bespoke_batch_file():
    """A hand-written uninstall batch would fight Inno Setup's own uninstaller.

    Inno Setup relocates its uninstaller to a temporary directory so it can
    delete the install folder. A second, parallel uninstall path would either
    duplicate that work or leave files behind.
    """
    for candidate in ("uninstall.bat", "Uninstall.bat", "uninstall.ps1"):
        assert not (PROJECT_ROOT / candidate).exists(), (
            f"{candidate} duplicates Inno Setup's own uninstaller"
        )
