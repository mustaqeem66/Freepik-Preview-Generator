import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.cli import cli_render_test, main_cli

pytestmark = pytest.mark.core


def test_cli_render_test_execution():
    """Verify PreviewGen --render-test renders an input asset to valid JPEG and returns 0."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        src = tmp / "fixture.png"
        out = tmp / "fixture_out.jpg"

        Image.new("RGBA", (150, 150), (100, 200, 50, 255)).save(src)

        exit_code = cli_render_test(str(src), str(out))
        assert exit_code == 0
        assert out.is_file()
        assert out.stat().st_size > 0
        with Image.open(out) as im:
            assert im.format == "JPEG"
            assert im.size == (150, 150)


def test_cli_render_test_honours_requested_raster_size():
    """A raster --size request downscales to the requested longest edge."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        src = tmp / "fixture.png"
        out = tmp / "fixture_out.jpg"

        Image.new("RGBA", (800, 400), (100, 200, 50, 255)).save(src)

        exit_code = cli_render_test(str(src), str(out), size=200)
        assert exit_code == 0
        with Image.open(out) as im:
            assert im.size == (200, 100)


def test_cli_size_flag_is_parsed_and_applied():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        src = tmp / "fixture.png"
        out = tmp / "fixture_out.jpg"
        Image.new("RGBA", (600, 600), (10, 20, 30, 255)).save(src)

        exit_code = main_cli(["--render-test", str(src), str(out), "--size", "300"])
        assert exit_code == 0
        with Image.open(out) as im:
            assert im.size == (300, 300)
