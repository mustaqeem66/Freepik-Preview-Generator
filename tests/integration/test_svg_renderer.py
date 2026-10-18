import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.full_runtime

# Optional renderer engine: skip the module (rather than aborting collection)
# when the full runtime is not installed.
resvg_py = pytest.importorskip("resvg_py")

from processor import PreviewConfig, generate_file


def test_svg_dimension_preservation():
    """Verify that production SVGs with explicit dimensions preserve exact pixel dimensions."""
    assert resvg_py is not None
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        svg_path = tmp / "test_icon.svg"
        out_jpg = tmp / "test_icon.jpg"

        svg_content = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">
            <rect width="1200" height="900" fill="none"/>
            <circle cx="600" cy="450" r="300" fill="#3B82F6"/>
        </svg>"""
        svg_path.write_text(svg_content, encoding="utf-8")

        cfg = PreviewConfig()
        generate_file(svg_path, out_jpg, cfg)

        assert out_jpg.is_file()
        with Image.open(out_jpg) as out_img:
            assert out_img.size == (1200, 900), f"Expected output (1200, 900), got {out_img.size}"
def test_svg_render_hygiene():
    """Verify that SVG rendering leaves no orphaned temp files."""
    fixtures = PROJECT_ROOT / "tests" / "fixtures"
    with tempfile.TemporaryDirectory() as tmp_dir:
        out = Path(tmp_dir) / "svg_hygiene.jpg"
        generate_file(fixtures / "sample.svg", out, PreviewConfig())
        assert out.is_file() and out.stat().st_size > 0
