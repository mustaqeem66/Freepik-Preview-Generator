"""Procreate nested brush tips render only on explicit contact-sheet opt-in."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image
import pytest

from previewgen.config import PreviewConfig
from previewgen.renderers.creator import _load_brushset_contact_sheet
from previewgen.renderers.loader import load_source_image

pytestmark = pytest.mark.core


def _nested_brush(color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGBA", (40, 40), (*color, 255))
    png = io.BytesIO()
    img.save(png, format="PNG")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as inner:
        inner.writestr("QuickLook/Thumbnail.png", png.getvalue())
    return data.getvalue()


def _brushset(path: Path, colors: list[tuple[int, int, int]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as outer:
        for index, color in enumerate(colors):
            outer.writestr(f"Brushes/tip-{index:02d}.brush", _nested_brush(color))


def test_four_nested_brush_tips_are_visible_in_synthetic_contact_sheet(tmp_path: Path):
    colors = [(220, 10, 20), (20, 210, 30), (30, 50, 215), (205, 180, 15)]
    path = tmp_path / "multi.brushset"
    _brushset(path, colors)
    original = path.read_bytes()
    default = load_source_image(path)
    assert default.size == (40, 40)

    sheet = load_source_image(
        path, config=PreviewConfig(brushset_contact_sheet=True), target_dimension=400
    )
    assert sheet.size == (400, 400)
    assert path.read_bytes() == original
    for point, expected in zip([(100, 100), (300, 100), (100, 300), (300, 300)], colors):
        assert sheet.getpixel(point)[:3] == expected


def test_never_decodes_more_than_nine_brush_tips(tmp_path: Path, monkeypatch):
    path = tmp_path / "crowded.brushset"
    _brushset(path, [(i * 14, i * 7, 20) for i in range(12)])
    import previewgen.renderers.creator as creator

    called = []
    original_decoder = creator._archive_image

    def traced(archive, name, nested=False):
        called.append(name)
        return original_decoder(archive, name, nested=nested)

    monkeypatch.setattr(creator, "_archive_image", traced)
    sheet = _load_brushset_contact_sheet(path, target_dimension=300)
    assert sheet.size == (300, 300)
    assert len([name for name in called if name.endswith(".brush")]) == 9


def test_missing_or_invalid_brush_is_explicit_failure(tmp_path: Path):
    path = tmp_path / "invalid.brushset"
    with zipfile.ZipFile(path, "w") as outer:
        outer.writestr("Brushes/bad.brush", b"not a ZIP archive")
    with pytest.raises(RuntimeError, match="Could not build brushset contact sheet"):
        _load_brushset_contact_sheet(path)


def test_config_default_off_and_strict_bool_contract():
    assert PreviewConfig.from_mapping({}).brushset_contact_sheet is False
    assert PreviewConfig.from_mapping(
        {"brushsetContactSheet": True}, mode="strict-export"
    ).brushset_contact_sheet is True
    with pytest.raises(ValueError, match="brushsetContactSheet"):
        PreviewConfig.from_mapping(
            {"brushsetContactSheet": "unsupported"}, mode="strict-export"
        )
