import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processor import PreviewConfig, generate_file

pytestmark = pytest.mark.core


def test_aspect_ratios_preserved_exactly():
    """Verify that any arbitrary aspect ratio (1:1, 4:3, 3:4, 16:9, 9:16) preserves its exact dimensions."""
    test_cases = [
        (1000, 1000, "1:1 Square"),
        (1600, 1200, "4:3 Landscape"),
        (1200, 1600, "3:4 Portrait"),
        (1920, 1080, "16:9 Widescreen"),
        (1080, 1920, "9:16 Mobile Vertical"),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        cfg = PreviewConfig()

        for w, h, label in test_cases:
            src = tmp / f"input_{w}x{h}.png"
            dst = tmp / f"output_{w}x{h}.jpg"

            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((w // 4, h // 4, 3 * w // 4, 3 * h // 4), fill=(99, 102, 241, 200))
            img.save(src, "PNG")

            generate_file(src, dst, cfg)

            assert dst.is_file(), f"Output file missing for {label}"
            with Image.open(dst) as out_img:
                assert out_img.size == (w, h), (
                    f"Dimension mismatch for {label}: Expected ({w}, {h}), got {out_img.size}"
                )
