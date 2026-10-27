"""Animated contact sheets are opt-in, capped, and match live/export loaders."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from previewgen.config import PreviewConfig
from previewgen.renderers.animation import animated_contact_sheet
from previewgen.renderers.loader import load_source_image

pytestmark = pytest.mark.core


def _gif(path: Path, colors: list[tuple[int, int, int]]) -> None:
    frames = [Image.new("RGB", (120, 120), color) for color in colors]
    frames[0].save(
        path, format="GIF", save_all=True, append_images=frames[1:],
        duration=100, loop=0, optimize=False,
    )


def test_four_frame_gif_centers_are_distinct_and_default_stays_first(tmp_path: Path):
    path = tmp_path / "animated.gif"
    colors = [(230, 0, 0), (0, 220, 0), (0, 0, 230), (210, 180, 0)]
    _gif(path, colors)
    default = load_source_image(path)
    assert default.size == (120, 120)
    assert default.getpixel((90, 90))[:3] == colors[0]

    config = PreviewConfig(animation_contact_sheet=True)
    with Image.open(path) as source:
        before_size = source.size
        sheet = animated_contact_sheet(source)
        assert source.size == before_size
    assert sheet.size == (120, 120)
    for point, expected in zip([(30, 30), (90, 30), (30, 90), (90, 90)], colors):
        actual = sheet.getpixel(point)[:3]
        assert all(abs(a - b) <= 5 for a, b in zip(actual, expected)), (point, actual, expected)

    loaded = load_source_image(path, config=config)
    assert loaded.tobytes() == sheet.tobytes()
    assert loaded.tobytes() != default.tobytes()


def test_contact_sheet_frame_limit_is_nine(tmp_path: Path):
    path = tmp_path / "12frames.gif"
    frames = [Image.new("RGB", (180, 180), (i * 17, i * 11, i * 9))
              for i in range(12)]
    frames[0].save(path, format="GIF", save_all=True,
                   append_images=frames[1:], duration=90, loop=0)
    with Image.open(path) as source:
        consumed = []
        original_seek = source.seek

        def counting_seek(index):
            consumed.append(index)
            return original_seek(index)

        source.seek = counting_seek
        contact = animated_contact_sheet(source)
    assert contact.size == (180, 180)
    assert max(consumed) == 8


def test_oversized_source_fails_before_decoding_frames():
    image = Image.new("RGB", (5000, 4000), "black")
    with pytest.raises(ValueError, match="16 MP"):
        animated_contact_sheet(image)


def test_single_frame_and_static_png_are_unchanged(tmp_path: Path):
    path = tmp_path / "static.png"
    Image.new("RGBA", (54, 63), (40, 80, 120, 220)).save(path)
    original = load_source_image(path)
    contact = load_source_image(path, config=PreviewConfig(animation_contact_sheet=True))
    assert original.size == contact.size
    assert original.tobytes() == contact.tobytes()


def test_setting_defaults_off_and_requires_boolean_in_strict_mode():
    assert PreviewConfig.from_mapping({}).animation_contact_sheet is False
    assert PreviewConfig.from_mapping(
        {"animationContactSheet": True}, mode="strict-export"
    ).animation_contact_sheet is True
    with pytest.raises(ValueError, match="animationContactSheet"):
        PreviewConfig.from_mapping(
            {"animationContactSheet": "not-a-boolean"}, mode="strict-export"
        )
