import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
pytestmark = pytest.mark.full_runtime
pytest.importorskip("psd_tools")
from psd_tools import PSDImage

from processor import PreviewConfig, generate_file


def test_psd_rendering_integration():
    """Verify PSD composite extraction and preview generation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        psd_path = tmp / "sample.psd"
        out_jpg = tmp / "sample.jpg"

        # Create a synthetic PSD image
        img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((50, 50, 250, 250), fill=(244, 63, 94, 220))
        psd = PSDImage.frompil(img)
        psd.save(psd_path)

        cfg = PreviewConfig()
        generate_file(psd_path, out_jpg, cfg)

        assert out_jpg.is_file()
        with Image.open(out_jpg) as out:
            assert out.size == (300, 300)
