import pytest

"""
Guards the canonical settings contract:

  * ``previewgen/settings_schema.json`` is the single source of truth.
  * The committed frontend TS contract must be exactly what the generator emits.
  * Every preview-affecting ``PreviewConfig`` field must be represented.
"""
import dataclasses
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import gen_settings_contract  # noqa: E402

from previewgen.config import PreviewConfig  # noqa: E402

pytestmark = pytest.mark.core

SCHEMA_PATH = PROJECT_ROOT / "previewgen" / "settings_schema.json"
CONTRACT_PATH = PROJECT_ROOT / "frontend" / "src" / "generated" / "settingsContract.ts"

# Not persisted as a user setting; derived from the freeform position controls.
_DERIVED_FIELDS = {"position"}


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def test_frontend_contract_is_up_to_date():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    expected = gen_settings_contract.build_contract(schema)
    committed = CONTRACT_PATH.read_text(encoding="utf-8")
    assert committed == expected, (
        "frontend/src/generated/settingsContract.ts is stale. "
        "Run: python scripts/gen_settings_contract.py"
    )


def test_schema_covers_every_preview_config_field():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    properties = set(schema.get("properties", {}))
    config_fields = {f.name for f in dataclasses.fields(PreviewConfig)}

    missing = {_camel(name) for name in config_fields} - properties - _DERIVED_FIELDS
    assert not missing, f"PreviewConfig fields missing from settings schema: {sorted(missing)}"
