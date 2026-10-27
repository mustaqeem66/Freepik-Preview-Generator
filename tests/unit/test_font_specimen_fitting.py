"""Typography specimen fitting stays inside card bounds for long labels."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from previewgen.renderers import font as font_renderer

pytestmark = pytest.mark.core


def _font(size: int) -> ImageFont.FreeTypeFont:
    # Pillow's built-in FreeType font avoids OS-specific installed paths.
    return ImageFont.load_default(size=size)


@pytest.mark.parametrize("width", [256, 850, 2400])
def test_specimen_text_stays_inside_card(monkeypatch, tmp_path: Path, width: int):
    monkeypatch.setattr(font_renderer, "load_typeface", lambda _path, size: _font(size))
    draws = []
    original_draw = ImageDraw.ImageDraw.text

    def traced(self, xy, value, *args, **kwargs):
        font = kwargs["font"]
        bounds = self.textbbox(xy, value, font=font)
        draws.append((value, bounds))
        return original_draw(self, xy, value, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", traced)
    source = tmp_path / ("extra-wide-font-name-" + "W" * 250 + ".ttf")
    result = font_renderer._load_font(source, target_dimension=width)
    assert result.size == (width, width)
    assert len(draws) == 8
    inner_right = width - round(width * 0.10)
    for value, bounds in draws:
        assert bounds[2] <= inner_right + 1, (value, bounds, inner_right)
    assert draws[0][0].endswith("...")  # label too wide even at min size
    assert result.getbbox() is not None


def test_short_font_title_keeps_original_size():
    image = Image.new("RGB", (400, 400))
    draw = ImageDraw.Draw(image)
    face = _font(36)
    text, fitted = font_renderer._fit_line(draw, "Short face", face, 300)
    assert text == "Short face"
    assert fitted.size == face.size


def test_extreme_label_is_bounded_and_indicated():
    image = Image.new("RGB", (400, 400))
    draw = ImageDraw.Draw(image)
    text, face = font_renderer._fit_line(draw, "W" * 2000, _font(38), 200)
    assert text.endswith("...")
    assert len(text) < 2000
    assert draw.textbbox((0, 0), text, font=face)[2] <= 200
