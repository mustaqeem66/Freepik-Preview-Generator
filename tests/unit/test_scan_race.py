import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


def test_desktop_api_overlapping_scan_race_prevention():
    """Verify that starting a second scan creates an independent context and cancels the prior scan."""
    api = DesktopApi()

    with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
        dir_a = Path(tmp_a)
        dir_b = Path(tmp_b)

        Image.new("RGBA", (50, 50), (255, 0, 0, 255)).save(dir_a / "a.png")
        Image.new("RGBA", (50, 50), (0, 255, 0, 255)).save(dir_b / "b.png")

        api._add_authorized_input_folder(dir_a)
        api._add_authorized_input_folder(dir_b)

        # 1. Start Scan A
        res_a = api.start_scan(str(dir_a))
        scan_id_a = res_a["scanId"]
        ctx_a = api.scanner.active_scan_context
        assert ctx_a is not None
        assert ctx_a.scan_id == scan_id_a
        assert not ctx_a.cancel_event.is_set()

        # 2. Immediately start Scan B (simulating rapid folder switching)
        res_b = api.start_scan(str(dir_b))
        scan_id_b = res_b["scanId"]
        ctx_b = api.scanner.active_scan_context
        assert ctx_b is not None
        assert ctx_b.scan_id == scan_id_b
        assert scan_id_a != scan_id_b

        # Scan A's private cancel_event must stay set
        assert ctx_a.cancel_event.is_set()
        # Scan B's private cancel_event must be clear
        assert not ctx_b.cancel_event.is_set()

        # Contexts and temp directories must be independent
        assert ctx_a.temp_root != ctx_b.temp_root
