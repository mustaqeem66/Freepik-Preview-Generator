"""A user must be able to tell which build they are running.

The install scripts resolve ``/releases/latest``, so the only code a user can
obtain is whatever was last published. This project sat for 139 commits with
the published release pinned at an old build: every merge, including the
security hardening, was invisible to anyone installing. Nothing failed,
because nothing checked, and the running app reported no version at all --
so a stale install and a current install were indistinguishable.

These tests pin the three surfaces that close that gap: the version the app
reports, the version the installers announce, and the gate that notices when
the tree has moved past the published release.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import previewgen  # noqa: E402
from previewgen.api import DesktopApi  # noqa: E402

pytestmark = pytest.mark.core

FRESHNESS_SCRIPT = PROJECT_ROOT / "scripts" / "check_release_freshness.py"


def _load_freshness_module():
    spec = importlib.util.spec_from_file_location("check_release_freshness", FRESHNESS_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_reports_the_running_version_and_platform():
    """The running build must identify itself.

    A user who installs from a script needs to confirm which build they got.
    Without this the version lives only in a Python constant, so a stale
    install and a current install look identical from the running app.
    """
    api = DesktopApi()
    try:
        response = api.get_app_info()
        assert response["ok"] is True
        assert response["error"] is None
        assert response["value"]["version"] == previewgen.__version__
        assert response["value"]["platform"] in {"windows", "linux", "macos", "unknown"}
    finally:
        api.cleanup()


def test_api_version_matches_the_packaging_identity():
    """The reported version must be the same version that is packaged.

    The installers and the Inno Setup script read the version from the tree,
    so a reported version that drifted from the packaged one would make the
    new signal lie.
    """
    api = DesktopApi()
    try:
        reported = api.get_app_info()["value"]["version"]
    finally:
        api.cleanup()

    assert reported == previewgen.__version__
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == reported


def test_installers_announce_the_release_they_install():
    """Each installer must say which release it is installing.

    The user's report was that an install produced an old, buggy build and
    nothing in the output said which build that was. Announcing the tag
    before the download lets a user catch it before installing.
    """
    powershell = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "Installing release:" in powershell
    assert "Release.tag_name" in powershell

    shell = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "Installing PreviewGen release:" in shell
    assert "tag_name" in shell


def test_installers_resolve_the_latest_published_release():
    """The installers must follow the newest published release.

    The stale build the user received came from the release side of the
    pipeline, not from a pinned version: the scripts resolve
    ``/releases/latest``, which is correct. This test pins that they keep
    doing so, so a future change cannot quietly reintroduce a hardcoded tag.
    """
    powershell = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "releases/latest" in powershell
    assert "releases/tags/" in powershell  # only for an explicit override

    shell = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "releases/latest" in shell
    assert "releases/tags/" in shell  # only for an explicit override


def test_freshness_gate_detects_a_release_that_is_behind_the_tree(monkeypatch):
    """A published release that lags the tree must be reported as stale.

    This is the exact condition that went unnoticed: the version and the
    published tag both stayed 2.1.2 while main carried 139 commits. A
    version-only comparison calls that "OK", so the gate must also count
    commits that the release does not contain.
    """
    module = _load_freshness_module()

    monkeypatch.setattr(module, "_latest_published_release", lambda repo: ("v2.1.2", "2026-10-20T16:17:25Z"))
    monkeypatch.setattr(module, "_unreleased_commit_count", lambda repo, tag: 139)
    monkeypatch.setattr(module, "_tree_version", lambda: "2.1.2")

    assert module.main([]) == 0  # reporting only never fails the build
    assert module.main(["--strict"]) == 1  # strict mode does fail


def test_freshness_gate_detects_a_version_that_moved_past_the_release(monkeypatch):
    """A bumped tree version with no matching release is stale too."""
    module = _load_freshness_module()

    monkeypatch.setattr(module, "_latest_published_release", lambda repo: ("v2.1.2", "2026-10-20T16:17:25Z"))
    monkeypatch.setattr(module, "_unreleased_commit_count", lambda repo, tag: 0)
    monkeypatch.setattr(module, "_tree_version", lambda: "2.1.3")

    assert module.main(["--strict"]) == 1


def test_freshness_gate_passes_when_the_release_covers_the_tree(monkeypatch):
    """A release that matches the tree and contains main is not stale."""
    module = _load_freshness_module()

    monkeypatch.setattr(module, "_latest_published_release", lambda repo: ("v2.1.3", "2026-11-22T00:00:00Z"))
    monkeypatch.setattr(module, "_unreleased_commit_count", lambda repo, tag: 0)
    monkeypatch.setattr(module, "_tree_version", lambda: "2.1.3")

    assert module.main([]) == 0
    assert module.main(["--strict"]) == 0


def test_freshness_gate_does_not_fail_the_build_when_the_api_is_unreachable(monkeypatch):
    """An unreachable API is not proof of a stale release.

    Failing every build because GitHub could not be reached would make the
    gate a source of false failures, so the unknown state reports and
    continues.
    """
    module = _load_freshness_module()

    monkeypatch.setattr(
        module,
        "_latest_published_release",
        lambda repo: (None, "could not reach the GitHub API: offline"),
    )

    assert module.main([]) == 0
    assert module.main(["--strict"]) == 1


def test_freshness_gate_reads_the_version_without_importing_the_package(monkeypatch):
    """The gate reads the declared version, so it works before a build."""
    module = _load_freshness_module()
    assert module._tree_version() == previewgen.__version__


def test_workflow_reports_release_freshness():
    """The build must surface the difference between tree and release."""
    workflow = (PROJECT_ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    assert "check_release_freshness.py" in workflow
