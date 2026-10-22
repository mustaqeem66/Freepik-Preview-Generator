"""Supported raster imports and protection of original input files."""
import hashlib
from pathlib import Path

import pytest
from PIL import Image

from previewgen.api import DesktopApi
from previewgen.batch.runner import process_folder
from previewgen.config import SUPPORTED_EXTENSIONS, PreviewConfig
from previewgen.destinations import protect_source_destinations

pytestmark = pytest.mark.core


def test_standard_raster_extensions_registered():
    assert {".jpg", ".jpeg", ".bmp", ".gif", ".ico"} <= set(SUPPORTED_EXTENSIONS)


@pytest.mark.parametrize("fmt, ext", [
    ("JPEG", ".jpg"), ("JPEG", ".jpeg"), ("BMP", ".bmp"),
    ("GIF", ".gif"), ("ICO", ".ico"),
])
def test_pillow_formats_decode(fmt, ext, tmp_path):
    from previewgen.renderers.loader import load_source_image

    file = tmp_path / ("sample" + ext)
    Image.new("RGB", (32, 32), (105, 125, 140)).save(file, format=fmt)
    image = load_source_image(file)
    assert image.size == (32, 32)
    assert image.mode == "RGBA"


def test_protect_sources_and_reserved_output_names(tmp_path):
    original = tmp_path / "piece.jpg"
    original.write_bytes(b"original")
    second = tmp_path / "piece_preview.jpg"
    second.write_bytes(b"another original")
    output = protect_source_destinations(
        original, {original.resolve(), second.resolve()}, {"piece_preview2.jpg"}
    )
    assert output.name == "piece_preview3.jpg"
    assert not output.exists()
    assert original.read_bytes() == b"original"


def test_single_jpeg_export_with_overwrite_never_mutates_input(tmp_path):
    file = tmp_path / "original.jpg"
    Image.new("RGB", (40, 40), "orange").save(file)
    original = file.read_bytes()
    api = DesktopApi()
    try:
        api._add_authorized_input_folder(tmp_path)
        result = api.export_preview(str(file), {
            "outputFolder": str(tmp_path), "overwritePolicy": "overwrite",
        })
        assert result["ok"], result
        output = Path(result["value"]["path"])
        assert output != file
        assert output.name.startswith("original_preview")
        assert file.read_bytes() == original
        assert output.is_file()
    finally:
        api.cleanup()


def test_batch_png_jpeg_same_stem_keeps_both_sources(tmp_path):
    first = tmp_path / "sample.png"
    second = tmp_path / "sample.jpg"
    Image.new("RGB", (48, 48), "red").save(first)
    Image.new("RGB", (48, 48), "blue").save(second)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (first, second)}
    report = process_folder(
        tmp_path, tmp_path, PreviewConfig(overwrite_policy="overwrite"),
        lambda *_: None, lambda: False,
    )
    assert report["success"] == 2, report
    for source in (first, second):
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before[source.name]
    outputs = {row["output"] for row in report["files"]}
    assert "sample.jpg" not in outputs
    assert len(outputs) == 2
