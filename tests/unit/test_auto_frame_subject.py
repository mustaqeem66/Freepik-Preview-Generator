"""Opt-in auto-frame preserves source pixels and canvas size."""
from __future__ import annotations

from PIL import Image, ImageDraw
import pytest

from previewgen.config import PreviewConfig
from previewgen.renderers.compose import _auto_frame_subject, compose_preview

pytestmark = pytest.mark.core


def _transparent_subject():
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((10, 15, 59, 64), fill=(220, 55, 70, 255))
    return image


def test_auto_frame_off_does_not_mutate_compositing_baseline():
    image = _transparent_subject()
    before = image.tobytes()
    output = compose_preview(image, PreviewConfig(text="", auto_frame=False))
    assert output.size == image.size
    assert image.tobytes() == before
    assert output.mode == "RGB"


def test_enabled_auto_frame_centers_subject_and_preserves_dimensions():
    image = _transparent_subject()
    before = image.tobytes()
    framed = _auto_frame_subject(image, margin=0.10)
    assert framed.size == image.size
    assert image.tobytes() == before
    bbox = framed.getchannel("A").getbbox()
    assert bbox is not None
    left, top, right, bottom = bbox
    assert left >= 30
    assert top >= 20
    assert right <= 270
    assert bottom <= 180
    assert abs((left + right) / 2 - image.width / 2) < 2
    assert abs((top + bottom) / 2 - image.height / 2) < 2

    config = PreviewConfig(text="", auto_frame=True, frame_margin=0.10)
    assert compose_preview(image, config).tobytes() != compose_preview(
        image, PreviewConfig(text="", auto_frame=False)
    ).tobytes()


def test_full_opaque_image_is_no_op():
    source = Image.new("RGBA", (96, 128), (12, 30, 65, 255))
    result = _auto_frame_subject(source, margin=0.25)
    assert result.tobytes() == source.tobytes()


def test_minuscule_subject_does_not_expand_more_than_4x():
    source = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    source.putpixel((5, 7), (255, 0, 0, 255))
    framed = _auto_frame_subject(source, margin=0)
    bbox = framed.getchannel("A").getbbox()
    assert bbox is not None
    assert bbox[2] - bbox[0] <= 4
    assert bbox[3] - bbox[1] <= 4


def test_auto_frame_settings_have_safe_defaults_and_bounds():
    config = PreviewConfig.from_mapping({"autoFrame": True, "frameMargin": 12}, mode="strict-export")
    assert config.auto_frame is True
    assert config.frame_margin == pytest.approx(0.12)
    assert PreviewConfig.from_mapping({}, mode="preview").auto_frame is False
    with pytest.raises(ValueError, match="frameMargin"):
        PreviewConfig.from_mapping({"frameMargin": 50}, mode="strict-export")
