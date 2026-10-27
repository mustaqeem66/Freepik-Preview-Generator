"""Tiled watermark must preserve regular placement and reuse shared composition."""
from __future__ import annotations

from PIL import Image, ImageChops
import pytest

from previewgen.config import PreviewConfig
from previewgen.renderers.compose import compose_preview

pytestmark = pytest.mark.core


def _colored_pixels(original: Image.Image, modified: Image.Image) -> int:
    diff = ImageChops.difference(original.convert("RGB"), modified.convert("RGB"))
    return sum(1 for pixel in diff.getdata() if max(pixel) > 0)


def test_tiled_watermark_is_bounded_repeated_and_preserves_source():
    source = Image.new("RGBA", (900, 900), (235, 235, 235, 255))
    before = source.tobytes()
    blank = compose_preview(source, PreviewConfig(text=""))
    tiled_config = PreviewConfig(
        text="PREVIEW", position="tiled", opacity=0.9,
        text_color=(0, 0, 0), has_outline=False,
    )
    tiled = compose_preview(source, tiled_config)
    assert tiled.size == blank.size == source.size
    assert tiled.mode == "RGB"
    assert source.tobytes() == before
    assert _colored_pixels(blank, tiled) > 1000

    for x in (0, 450):
        for y in (0, 450):
            box = (x, y, x + 450, y + 450)
            assert _colored_pixels(blank.crop(box), tiled.crop(box)) > 20


def test_tiled_zero_opacity_matches_text_free_composite():
    source = Image.new("RGBA", (512, 300), (50, 90, 120, 255))
    blank = compose_preview(source, PreviewConfig(text=""))
    tiled = compose_preview(
        source, PreviewConfig(text="INVISIBLE", position="tiled", opacity=0)
    )
    assert tiled.tobytes() == blank.tobytes()


def test_tiled_position_validates_through_canonical_bridge_mapping():
    config = PreviewConfig.from_mapping(
        {"position": "tiled", "text": "PREVIEW", "opacity": 65}, mode="strict-export"
    )
    assert config.position == "tiled"
    assert config.opacity == pytest.approx(0.65)
    assert PreviewConfig.from_mapping({}, mode="strict-export").position == "custom"


@pytest.mark.parametrize("position", ["custom", "top-left", "top-right", "center", "bottom-left", "bottom-right"])
def test_existing_positions_still_generate_nonblank_image(position: str):
    source = Image.new("RGBA", (380, 240), (200, 90, 50, 255))
    image = compose_preview(
        source, PreviewConfig(text="LABEL", position=position, text_color=(20, 20, 20))
    )
    assert image.size == source.size
    assert image.mode == "RGB"
