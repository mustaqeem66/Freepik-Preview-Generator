from pathlib import Path
import sys
import tempfile
import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.cli import cli_render_test


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