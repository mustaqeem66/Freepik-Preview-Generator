"""
Unit tests for monotonic settings revision ordering.

Settings writes can be triggered in quick succession (debounced UI updates,
retries). A write that carries an older revision must never overwrite a newer
one, regardless of the order in which the writes complete.
"""
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import settings as settings_module

pytestmark = pytest.mark.core


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.v1.json")
    monkeypatch.setattr(settings_module, "SETTINGS_BACKUP", tmp_path / "settings.v1.json.bak")
    monkeypatch.setattr(settings_module, "_current_revision", 0)
    return tmp_path


def _persisted() -> dict:
    return json.loads(settings_module.SETTINGS_FILE.read_text(encoding="utf-8"))


def test_stale_write_is_rejected(isolated_settings):
    assert settings_module.save_settings({"text": "newest", "revision": 10}) is True
    assert settings_module.get_current_revision() == 10

    assert settings_module.save_settings({"text": "stale", "revision": 8}) is False

    data = _persisted()
    assert data["revision"] == 10
    assert data["text"] == "newest"


def test_out_of_order_writes_keep_highest_revision(isolated_settings):
    # A newer write lands first, then an older in-flight write completes late.
    assert settings_module.save_settings({"text": "first", "revision": 7}) is True
    assert settings_module.save_settings({"text": "second-stale", "revision": 6}) is False

    assert settings_module.get_current_revision() == 7
    assert _persisted()["text"] == "first"


def test_equal_and_increasing_revisions_are_accepted(isolated_settings):
    assert settings_module.save_settings({"text": "a", "revision": 3}) is True
    # Equal revision is not "older" and must be allowed (idempotent retry).
    assert settings_module.save_settings({"text": "b", "revision": 3}) is True
    assert settings_module.save_settings({"text": "c", "revision": 4}) is True
    assert settings_module.get_current_revision() == 4
    assert _persisted()["revision"] == 4


def test_revisionless_write_does_not_lower_the_floor(isolated_settings):
    assert settings_module.save_settings({"text": "with-rev", "revision": 5}) is True
    assert settings_module.save_settings({"text": "no-rev"}) is True
    assert settings_module.get_current_revision() == 5
    # A later stale write is still rejected against the retained floor.
    assert settings_module.save_settings({"text": "old", "revision": 4}) is False


def test_load_restores_revision_floor(isolated_settings):
    assert settings_module.save_settings({"text": "persisted", "revision": 9}) is True

    # Fresh process: in-memory revision is reset before loading from disk.
    settings_module._current_revision = 0
    loaded = settings_module.load_settings()

    assert loaded["revision"] == 9
    assert settings_module.get_current_revision() == 9


def test_api_save_settings_persists_revision_and_rejects_stale(isolated_settings):
    from previewgen.api import DesktopApi

    api = DesktopApi()
    try:
        accepted = api.save_settings({"text": "hello", "revision": 1})
        assert accepted["ok"] is True, accepted
        assert _persisted()["revision"] == 1
        assert _persisted()["text"] == "hello"

        # A newer revision from another instance raises the floor.
        settings_module.set_current_revision(5)
        rejected = api.save_settings({"text": "older", "revision": 2})
        assert rejected["ok"] is False
        assert "Stale" in (rejected["error"] or "")
        assert _persisted()["text"] == "hello"
    finally:
        api.cleanup()
