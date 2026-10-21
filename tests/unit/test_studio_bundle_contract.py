"""Prevent release of an accidentally cached pre-redesign Studio bundle."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_studio_bundle import inspect_bundle

pytestmark = pytest.mark.core


def test_missing_built_app_fails_with_actionable_remediation(tmp_path: Path) -> None:
    result = inspect_bundle(tmp_path / "dist" / "index.html")
    assert any("npm run build" in message for message in result)


def test_compiled_bundle_must_contain_new_ui_contract(tmp_path: Path) -> None:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text('<div id="root"></div>')
    (root / "assets" / "index.css").write_text(".canvas-export-dock{} .precision-slider{}")
    (root / "assets" / "index.js").write_text("canvas-export-dock")
    missing = inspect_bundle(root / "index.html")
    assert "Compiled CSS missing .inspector-scroll-content" in missing
    assert "Compiled CSS missing .library-scroll-content" in missing
    assert "Compiled JS missing inspector-scroll-content" in missing


def test_current_compiled_bundle_passes(tmp_path: Path) -> None:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text('<div id="root"></div>')
    (root / "assets" / "index.css").write_text(
        ".canvas-export-dock{}.precision-slider{}.library-scroll-content{}.inspector-scroll-content{}"
    )
    (root / "assets" / "index.js").write_text(
        'className:"canvas-export-dock";className:"inspector-scroll-content";'
    )
    assert inspect_bundle(root / "index.html") == []
