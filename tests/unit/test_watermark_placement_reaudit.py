"""Render contract: preset placement is honored rather than overridden."""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from previewgen.config import PreviewConfig
from previewgen.renderers.compose import _calculate_text_position, compose_preview

pytestmark = pytest.mark.core


def test_object_center_position_uses_nontransparent_artwork_bounds():
    assert _calculate_text_position(
        (400, 400), (40, 20), "center", (280, 230, 360, 310)
    ) == (300, 260)


def test_compositor_observes_backend_position_preset():
    original = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    ImageDraw.Draw(original).rectangle((230, 210, 380, 360), fill=(220, 90, 60, 255))
    centered = PreviewConfig.from_mapping(
        {"position": "center", "text": "WATERMARK", "opacity": 100},
        mode="strict-export",
    )
    custom = PreviewConfig.from_mapping(
        {"position": "custom", "text": "WATERMARK", "opacity": 100,
         "textPosX": 5, "textPosY": 5},
        mode="strict-export",
    )
    assert centered.position == "center"
    assert custom.position == "custom"
    center_pixels = compose_preview(original, centered).tobytes()
    custom_pixels = compose_preview(original, custom).tobytes()
    assert center_pixels != custom_pixels
