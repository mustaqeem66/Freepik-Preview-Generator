"""DXF renders must honour the requested export dimension (P0-3).

``ezdxf``'s ``MatplotlibBackend.finalize()`` resizes the figure to the drawing
extents using matplotlib's default base size, so the requested dimension was
silently discarded (~960px regardless of 1024/2400/4096).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.renderers.cad import _load_dxf  # noqa: E402

pytestmark = pytest.mark.full_runtime

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "sample.dxf"


@pytest.mark.parametrize("target", [512, 1024, 2400])
def test_dxf_render_matches_requested_longest_edge(target: int):
    pytest.importorskip("ezdxf")
    pytest.importorskip("matplotlib")
    assert FIXTURE.is_file(), f"missing fixture: {FIXTURE}"

    image = _load_dxf(FIXTURE, target_dimension=target)

    assert max(image.size) == target
    assert image.mode == "RGBA"
