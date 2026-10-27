"""
Unit tests for canonical settings schema wiring.

The settings schema (previewgen/settings_schema.json) is the shared contract
between the frontend and backend. These tests verify the validator and that
persistence only ever writes schema-valid values.
"""
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import settings as settings_module
from previewgen.settings_schema import sanitize_settings, validate_settings

pytestmark = pytest.mark.core


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(settings_module, "SETTINGS_FILE", tmp_path / "settings.v1.json")
    monkeypatch.setattr(settings_module, "SETTINGS_BACKUP", tmp_path / "settings.v1.json.bak")
    return tmp_path


def test_schema_accepts_valid_payload():
    assert validate_settings(
        {"schemaVersion": 2, "text": "hello", "logoScale": 100, "theme": "dark"}
    ) == []


@pytest.mark.parametrize(
    "payload,fragment",
    [
        ({"schemaVersion": 2, "solidColor": "red"}, "pattern"),
        ({"schemaVersion": 2, "outlineThickness": 99}, "maximum"),
        ({"schemaVersion": 2, "opacity": -5}, "minimum"),
        ({"schemaVersion": 2, "theme": "neon"}, "one of"),
        ({"schemaVersion": 2, "bogus": 1}, "unexpected property"),
        ({"text": "x"}, "missing required property"),
    ],
)
def test_schema_rejects_invalid_payload(payload, fragment):
    errors = validate_settings(payload)
    assert any(fragment in e for e in errors), errors


def test_watermark_placement_schema_validates_presets():
    assert validate_settings({"schemaVersion": 2, "position": "center"}) == []
    assert validate_settings({"schemaVersion": 2, "position": "bottom-right"}) == []
    assert any("one of" in error for error in validate_settings(
        {"schemaVersion": 2, "position": "diagonal-tiled"}
    ))


def test_auto_frame_schema_bounds_and_default_off():
    assert validate_settings({"schemaVersion": 2, "autoFrame": True, "frameMargin": 12}) == []
    assert any("maximum" in error for error in validate_settings(
        {"schemaVersion": 2, "frameMargin": 50}
    ))


def test_sanitize_drops_unknown_and_invalid():
    clean = sanitize_settings(
        {"schemaVersion": 1, "text": "ok", "solidColor": "red", "junk": 1, "outlineThickness": 3}
    )
    assert clean == {"text": "ok", "outlineThickness": 3}


def test_save_settings_persists_only_valid_keys(isolated_settings):
    ok = settings_module.save_settings(
        {"text": "banner", "solidColor": "not-a-color", "unknownKey": 5, "logoScale": 100}
    )
    assert ok is True

    written = json.loads((isolated_settings / "settings.v1.json").read_text(encoding="utf-8"))
    assert written["schemaVersion"] == 2
    assert written["text"] == "banner"
    assert written["logoScale"] == 100
    assert "solidColor" not in written
    assert "unknownKey" not in written


def test_load_settings_sanitizes_corrupt_file(isolated_settings):
    (isolated_settings / "settings.v1.json").write_text(
        json.dumps({"schemaVersion": 1, "text": "keep", "opacity": 999, "bogus": True}),
        encoding="utf-8",
    )
    loaded = settings_module.load_settings()
    assert loaded["schemaVersion"] == 2
    assert loaded["text"] == "keep"
    assert "opacity" not in loaded
    assert "bogus" not in loaded
