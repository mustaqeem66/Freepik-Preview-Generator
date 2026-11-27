"""Fail-closed checker for the packaged native render-evidence marker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_render_marker import main

pytestmark = pytest.mark.core


def _write_marker(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_render_marker_requires_a_meaningful_root(tmp_path: Path) -> None:
    marker = _write_marker(
        tmp_path / "render.json",
        {
            "ok": True,
            "rootChildCount": 3,
            "rootWidth": 1400,
            "rootHeight": 900,
            "textLength": 20,
            "error": None,
        },
    )

    assert main(["--marker", str(marker)]) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": False, "rootChildCount": 0, "rootWidth": 1400, "rootHeight": 900, "textLength": 0},
        {"ok": True, "rootChildCount": 0, "rootWidth": 1400, "rootHeight": 900, "textLength": 20},
        {"ok": True, "rootChildCount": 3, "rootWidth": 0, "rootHeight": 900, "textLength": 20},
        {"ok": True, "rootChildCount": 3, "rootWidth": 1400, "rootHeight": 0, "textLength": 20},
        {"ok": True, "rootChildCount": 3, "rootWidth": 1400, "rootHeight": 900, "textLength": 0},
    ],
)
def test_render_marker_rejects_blank_or_invalid_dom(tmp_path: Path, payload: dict) -> None:
    marker = _write_marker(tmp_path / "render.json", payload)

    assert main(["--marker", str(marker)]) == 1


def test_render_marker_requires_a_real_json_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert main(["--marker", str(missing)]) == 2

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert main(["--marker", str(invalid)]) == 2
