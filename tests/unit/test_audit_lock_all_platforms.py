"""Tests for the platform-neutral Python lock projection used by the advisory gate.

pip-audit skips a pin whose PEP 508 environment marker does not match the host
it runs on. A universal lock therefore audits only part of its pins on any one
runner. These tests pin the behaviour that makes every pin auditable.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.audit_lock_all_platforms import neutralize_markers

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parent.parent.parent


def test_windows_marker_is_neutralized():
    projected = neutralize_markers("clr-loader==0.3.1 ; sys_platform == 'win32' \\")
    assert "sys_platform" not in projected
    assert "clr-loader==0.3.1" in projected


def test_macos_marker_is_neutralized():
    projected = neutralize_markers("pyobjc-core==12.2.2 ; sys_platform == 'darwin' \\")
    assert "sys_platform" not in projected
    assert "pyobjc-core==12.2.2" in projected


def test_platform_system_and_os_name_are_neutralized():
    projected = neutralize_markers(
        "pkg==1.0 ; platform_system == 'Windows' \\\\\n    --hash=sha256:"
        + "a" * 64
        + "\n"
        "other==2.0 ; os_name == 'nt' \\"
    )
    assert "platform_system" not in projected
    assert "os_name" not in projected


def test_version_markers_are_preserved():
    # A version gate describes which Python a pin applies to; rewriting it
    # would change what the pin means rather than which platform sees it.
    source = "numpy==2.4.3 ; python_version >= '3.12' \\"
    assert neutralize_markers(source) == source


def test_pin_count_is_preserved():
    for lock in ("requirements-lock.txt", "requirements-dev-lock.txt",
                 "requirements-linux-gui-lock.txt"):
        source = (ROOT / lock).read_text(encoding="utf-8")
        projected = neutralize_markers(source)
        assert source.count("\n") == projected.count("\n")
        pins = [line for line in projected.splitlines() if line[:1].isalpha()]
        assert pins, f"{lock} has no pins"


def test_no_platform_marker_survives_in_the_committed_locks():
    for lock in ("requirements-lock.txt", "requirements-dev-lock.txt",
                 "requirements-linux-gui-lock.txt"):
        projected = neutralize_markers((ROOT / lock).read_text(encoding="utf-8"))
        for marker in ("sys_platform", "platform_system", "os_name"):
            assert marker not in projected, f"{lock} still gates a pin on {marker}"


def test_every_platform_gated_pin_is_auditable():
    """A known Windows-only pin must survive the projection intact."""
    source = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")
    assert "sys_platform == 'win32'" in source, "fixture expectation changed"
    projected = neutralize_markers(source)
    assert "clr-loader==0.3.1" in projected
    assert "pythonnet==3.2.1" in projected


def test_script_reports_a_missing_lock(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from scripts.audit_lock_all_platforms import main

    code = main(["audit_lock_all_platforms.py", str(tmp_path / "nope.txt")])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_script_refuses_to_overwrite_an_existing_projection(tmp_path: Path):
    from scripts.audit_lock_all_platforms import main

    lock = tmp_path / "requirements-lock.txt"
    lock.write_text("pkg==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
    target = tmp_path / "projection.txt"
    target.write_text("existing", encoding="utf-8")

    code = main([
        "audit_lock_all_platforms.py", str(lock),
        "--project-out", str(target), "--python", sys.executable,
    ])
    assert code == 2
    assert target.read_text(encoding="utf-8") == "existing"
