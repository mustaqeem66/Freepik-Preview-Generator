"""Regressions for renderer defects found in the backend audit.

The .ai case matters most: pypdfium2 hands out PdfPage and PdfBitmap objects
that are not context managers, so the high-resolution path raised TypeError on
every single Illustrator file and the broad ``except`` dropped it to the
embedded XMP thumbnail -- a blurry export that the batch report called success.
"""
from __future__ import annotations

import base64
import io
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import config as previewgen_config
from previewgen.config import PreviewConfig
from previewgen.errors import ErrorCode, classify_exception
from previewgen.renderers.compose import compose_preview
from previewgen.renderers.loader import load_source_image
from previewgen.renderers.proprietary import extract_f3d_thumbnail
from previewgen.renderers.vector import _load_ai

pytestmark = pytest.mark.core


def _pdf_bytes(size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, format="PDF")
    return buf.getvalue()


def _xmp_thumbnail(size: tuple[int, int]) -> bytes:
    """The embedded-preview block Illustrator writes into a dual-stream file."""
    buf = io.BytesIO()
    Image.new("RGB", size, "blue").save(buf, format="JPEG")
    return (
        f"<xmpGImg:image>{base64.b64encode(buf.getvalue()).decode()}</xmpGImg:image>".encode()
    )


def test_ai_uses_the_vector_page_not_the_embedded_thumbnail(tmp_path):
    source = tmp_path / "artwork.ai"
    source.write_bytes(_pdf_bytes((1200, 900)) + _xmp_thumbnail((150, 112)))

    rendered = _load_ai(source, target_dimension=2400)

    assert rendered.size == (2400, 1800), (
        "the render fell back to the XMP thumbnail instead of rasterizing the page"
    )


def test_ai_still_falls_back_to_the_thumbnail_when_not_pdf_compatible(tmp_path):
    # Illustrator 8 and earlier ship a non-PDF stream; the thumbnail is the
    # only thing available and must still produce an image rather than raise.
    source = tmp_path / "legacy.ai"
    source.write_bytes(b"%!PS-Adobe-3.0 postscript only" + _xmp_thumbnail((150, 112)))

    rendered = _load_ai(source, target_dimension=2400)

    assert rendered.size == (150, 112)


def test_f3d_keeps_looking_after_an_oversized_thumbnail(tmp_path, monkeypatch):
    monkeypatch.setattr(previewgen_config, "MAX_EMBEDDED_THUMBNAIL_BYTES", 4096)
    archive = tmp_path / "part.f3d"
    small = io.BytesIO()
    Image.new("RGB", (64, 64), "green").save(small, format="PNG")
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Thumbnail/large.png", b"\x00" * 8192)
        zf.writestr("Thumbnail/small.png", small.getvalue())

    thumb = extract_f3d_thumbnail(archive)

    assert thumb is not None, "the oversized first member aborted the search"
    assert thumb.size == (64, 64)


def test_unusable_logo_fails_the_composite_instead_of_dropping_branding(tmp_path):
    """A requested logo that cannot be read must not yield an unbranded success."""
    logo = tmp_path / "brand.png"
    logo.write_bytes(b"not a png")
    source = Image.new("RGBA", (200, 150), (10, 200, 60, 255))
    config = PreviewConfig(text="PREVIEW", logo_path=str(logo))

    with pytest.raises(Exception) as caught:
        compose_preview(source, config=config)

    code, _message = classify_exception(caught.value)
    assert code == ErrorCode.CORRUPT_ASSET


@pytest.mark.parametrize(("mode", "peak"), [("F", 1.0), ("I", 255), ("I", 65535), ("I;16", 65535)])
def test_numeric_rasters_are_stretched_to_a_visible_range(tmp_path, mode, peak):
    """A normalized float or 8-bit-range integer file used to render black."""
    path = tmp_path / f"numeric-{mode.replace(';', '_')}-{int(peak)}.tif"
    image = Image.new(mode, (64, 64))
    image.putdata([peak * (i % 64) / 63 for i in range(64 * 64)])
    image.save(path)

    rendered = load_source_image(path).convert("L")

    assert rendered.getextrema()[1] >= 250, f"{mode} data peaked at {peak} rendered too dark"


def test_valid_logo_is_actually_composited(tmp_path):
    """Guards the branding path itself: the logo must land on the canvas."""
    logo = tmp_path / "brand.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(logo)
    source = Image.new("RGBA", (200, 150), (0, 200, 0, 255))
    config = PreviewConfig(
        text="", logo_path=str(logo), logo_scale=3.0, logo_opacity=1.0,
        logo_pos_x=0.0, logo_pos_y=0.0,
    )

    result = compose_preview(source, config=config).convert("RGB")

    assert result.getpixel((5, 5)) == (255, 0, 0)
    assert result.getpixel((195, 145)) != (255, 0, 0)
