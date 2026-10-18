"""
PreviewGen Settings Schema Validation
GUI-independent, dependency-free validator for the canonical settings schema.

The same ``settings_schema.json`` is the single source of truth shared with the
frontend. This module supports the JSON Schema subset used by that document
(objects, properties, required, additionalProperties, type, enum, const,
pattern, minimum, maximum, maxLength) so no third-party validator is required.
"""
from __future__ import annotations

import json
import logging
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("settings_schema.json")


@lru_cache(maxsize=1)
def get_schema() -> dict[str, Any]:
    """Load and cache the canonical settings schema."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_properties() -> set[str]:
    """Names of the top-level settings keys defined by the schema."""
    return set(get_schema().get("properties", {}).keys())


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True  # unknown/unsupported type keywords are not enforced


def _validate(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    label = path or "<root>"

    if "const" in schema and value != schema["const"]:
        errors.append(f"{label}: must equal {schema['const']!r}")

    expected = schema.get("type")
    if expected and not _type_ok(value, expected):
        errors.append(f"{label}: expected {expected}, got {type(value).__name__}")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{label}: must be one of {schema['enum']}")

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(pattern, value) is None:
            errors.append(f"{label}: does not match pattern {pattern}")
        max_length = schema.get("maxLength")
        if max_length is not None and len(value) > max_length:
            errors.append(f"{label}: exceeds maxLength {max_length}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            errors.append(f"{label}: must be finite")
            return
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            errors.append(f"{label}: below minimum {minimum}")
        if maximum is not None and value > maximum:
            errors.append(f"{label}: above maximum {maximum}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{label}.{key}: unexpected property")
        for required in schema.get("required", []):
            if required not in value:
                errors.append(f"{label}: missing required property '{required}'")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                _validate(child, child_schema, f"{label}.{key}" if path else key, errors)


def validate_settings(payload: Any) -> list[str]:
    """Validate a settings payload against the canonical schema.

    Returns a list of human-readable error messages (empty when valid).
    """
    errors: list[str] = []
    _validate(payload, get_schema(), "", errors)
    return errors


def sanitize_settings(payload: Any) -> dict[str, Any]:
    """Return a settings dict containing only schema-valid top-level values.

    Unknown keys and values that individually fail validation are dropped so a
    partial/corrupt payload can never be persisted or surfaced to the UI.
    """
    if not isinstance(payload, dict):
        return {}
    properties = get_schema().get("properties", {})
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        child_schema = properties.get(key)
        if not isinstance(child_schema, dict):
            continue
        errors: list[str] = []
        _validate(value, child_schema, key, errors)
        if errors:
            logging.warning("Dropping invalid setting '%s': %s", key, "; ".join(errors))
            continue
        clean[key] = value
    return clean
