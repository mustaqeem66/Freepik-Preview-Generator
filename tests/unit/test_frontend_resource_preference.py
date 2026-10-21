"""A rebuilt Vite UI must win over stale copied packaging assets."""
from __future__ import annotations

import sys
from pathlib import Path

from previewgen import resources


def test_unfrozen_runtime_prefers_canonical_frontend_dist(monkeypatch, tmp_path: Path):
    root = tmp_path / "checkout"
    package = root / "previewgen"
    package.mkdir(parents=True)
    primary = root / "frontend" / "dist" / "index.html"
    stale = package / "frontend" / "dist" / "index.html"
    for path in (primary, stale):
        path.parent.mkdir(parents=True)
        path.write_text(path.as_posix())
    monkeypatch.setattr(resources, "__file__", str(package / "resources.py"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert resources.get_html_dist() == primary


def test_unfrozen_fallback_when_canonical_dist_missing(monkeypatch, tmp_path: Path):
    package = tmp_path / "previewgen"
    stale = package / "frontend" / "dist" / "index.html"
    stale.parent.mkdir(parents=True)
    stale.write_text("legacy")
    monkeypatch.setattr(resources, "__file__", str(package / "resources.py"))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert resources.get_html_dist() == stale


def test_frozen_uses_only_bundle_resources(monkeypatch, tmp_path: Path):
    package = tmp_path / "repo" / "previewgen"
    package.mkdir(parents=True)
    new_checkout = package.parent / "frontend" / "dist" / "index.html"
    new_checkout.parent.mkdir(parents=True)
    new_checkout.write_text("not the bundled UI")
    bundle = tmp_path / "frozen" / "frontend" / "dist" / "index.html"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("ship")
    monkeypatch.setattr(resources, "__file__", str(package / "resources.py"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle.parent.parent.parent), raising=False)
    assert resources.get_html_dist() == bundle
