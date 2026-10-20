"""Export-size control: asset classification, native probing, and clamped sizing."""
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.assets import (  # noqa: E402
    RASTER,
    VECTOR,
    probe_asset,
)
from previewgen.config import MAX_EXPORT_DIMENSION, PreviewConfig  # noqa: E402
from previewgen.renderers.pipeline import generate_file  # noqa: E402

pytestmark = pytest.mark.core


def _write_png(path: Path, size: tuple[int, int]) -> None:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((size[0] // 4, size[1] // 4, 3 * size[0] // 4, 3 * size[1] // 4), fill=(99, 102, 241, 255))
    img.save(path, "PNG")




def test_probe_reports_native_size_for_raster():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "canvas.png"
        _write_png(src, (1600, 1200))
        probe = probe_asset(src)
        assert probe["kind"] == RASTER
        assert probe["resizable"] is False
        assert (probe["nativeWidth"], probe["nativeHeight"]) == (1600, 1200)
        assert probe["maxDimension"] == MAX_EXPORT_DIMENSION


def test_probe_reports_declared_svg_size():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "icon.svg"
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="128"></svg>', encoding="utf-8")
        probe = probe_asset(src)
        assert probe["kind"] == VECTOR
        assert probe["resizable"] is True
        assert (probe["nativeWidth"], probe["nativeHeight"]) == (256, 128)


def test_probe_uses_viewbox_when_no_width_height():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "vb.svg"
        src.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480"></svg>', encoding="utf-8")
        probe = probe_asset(src)
        assert (probe["nativeWidth"], probe["nativeHeight"]) == (640, 480)


def test_raster_export_downscales_to_requested_size():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "big.png"
        out = Path(tmp) / "big.jpg"
        _write_png(src, (1600, 1200))
        cfg = PreviewConfig(output_width=800, output_height=600)
        generate_file(src, out, cfg)
        with Image.open(out) as img:
            assert img.size == (800, 600)


def test_raster_export_never_upscales():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "small.png"
        out = Path(tmp) / "small.jpg"
        _write_png(src, (400, 300))
        cfg = PreviewConfig(output_width=2000, output_height=1500)
        generate_file(src, out, cfg)
        with Image.open(out) as img:
            assert img.size == (400, 300), "raster must be clamped to its native pixels"


def test_zero_output_size_keeps_native_dimensions():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "native.png"
        out = Path(tmp) / "native.jpg"
        _write_png(src, (640, 640))
        generate_file(src, out, PreviewConfig())
        with Image.open(out) as img:
            assert img.size == (640, 640)


def test_vector_export_upscales_to_requested_size():
    pytest.importorskip("resvg_py")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "icon.svg"
        out = Path(tmp) / "icon.jpg"
        src.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
            '<rect width="100" height="100" fill="#6366F1"/></svg>',
            encoding="utf-8",
        )
        cfg = PreviewConfig(output_width=512, output_height=512)
        generate_file(src, out, cfg)
        with Image.open(out) as img:
            assert img.size == (512, 512)


def test_preview_mode_clamps_output_size_to_cap():
    cfg = PreviewConfig.from_mapping({"outputWidth": 50_000, "outputHeight": 50_000}, mode="preview")
    assert cfg.output_width == MAX_EXPORT_DIMENSION
    assert cfg.output_height == MAX_EXPORT_DIMENSION


def test_strict_mode_rejects_output_size_over_cap():
    with pytest.raises(ValueError):
        PreviewConfig.from_mapping({"outputWidth": MAX_EXPORT_DIMENSION + 1, "outputHeight": 100}, mode="strict-export")


def test_strict_mode_accepts_output_size_within_cap():
    cfg = PreviewConfig.from_mapping({"outputWidth": 1024, "outputHeight": 768}, mode="strict-export")
    assert (cfg.output_width, cfg.output_height) == (1024, 768)


def test_api_probe_and_export_round_trip():
    from previewgen.api import DesktopApi

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "art.png"
        _write_png(src, (1200, 900))
        out_dir = tmp_path / "exports"

        api = DesktopApi()
        api.add_authorized_folder(tmp_path)
        probe = api.probe_asset(str(src))
        assert probe["ok"] is True
        assert probe["value"]["nativeWidth"] == 1200
        assert probe["value"]["nativeHeight"] == 900

        res = api.export_preview(
            str(src),
            {"outputWidth": 600, "outputHeight": 450, "outputFolder": str(out_dir)},
        )
        assert res["ok"] is True, res
        assert (res["value"]["width"], res["value"]["height"]) == (600, 450)
        assert Path(res["value"]["path"]).is_file()


def test_api_probe_reports_missing_file():
    from previewgen.api import DesktopApi

    with tempfile.TemporaryDirectory() as tmp:
        api = DesktopApi()
        result = api.probe_asset(str(Path(tmp) / "does-not-exist.png"))
        assert result["ok"] is False

