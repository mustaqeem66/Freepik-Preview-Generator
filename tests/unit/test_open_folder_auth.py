"""
Regression tests for the P0 hardening of ``DesktopApi.open_folder``.

The method is reachable through the privileged JS bridge, so it must:
  * reject paths outside explicitly authorized application-owned roots,
  * reject missing directories instead of creating them,
  * never invoke the OS file explorer for unauthorized/missing paths.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


@pytest.fixture
def launched(monkeypatch):
    """Capture any attempt to hand a path to the OS file explorer."""
    calls: list = []

    def fake_popen(args, *a, **k):
        calls.append(args)
        return None

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", fake_popen)
    def fake_startfile(path):  # pragma: no cover - win32 only
        calls.append(path)

    monkeypatch.setattr("os.startfile", fake_startfile, raising=False)
    return calls


def test_open_folder_rejects_unregistered_path(launched):
    api = DesktopApi()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp).resolve()
        result = api.open_folder(str(target))

    assert result["ok"] is False
    assert result["error"] == "UNAUTHORIZED_PATH"
    assert launched == []


def test_open_folder_opens_registered_path(launched):
    api = DesktopApi()
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp).resolve()
        api.add_authorized_folder(target)
        result = api.open_folder(str(target))

    assert result["ok"] is True
    assert len(launched) == 1


def test_open_folder_allows_subdirectory_of_registered_root(launched):
    api = DesktopApi()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        child = root / "nested" / "child"
        child.mkdir(parents=True)
        api.add_authorized_folder(root)
        result = api.open_folder(str(child))

    assert result["ok"] is True
    assert len(launched) == 1


def test_open_folder_rejects_missing_without_creating_it(launched):
    api = DesktopApi()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        api.add_authorized_folder(root)
        missing = root / "does_not_exist"
        result = api.open_folder(str(missing))

        assert result["ok"] is False
        assert result["error"] == "FOLDER_NOT_FOUND"
        assert not missing.exists()
    assert launched == []


def test_open_folder_rejects_empty_path(launched):
    api = DesktopApi()
    assert api.open_folder("")["ok"] is False
    assert api.open_folder("   ")["ok"] is False
    assert launched == []
