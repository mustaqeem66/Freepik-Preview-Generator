"""CAD renderer regressions: IGES reader selection and DWG thumbnail records."""
from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.core


def _write_single_record_dwg(path: Path) -> None:
    """A DWG header with exactly one BMP preview record.

    The embedded payload starts at the BITMAPINFOHEADER (not the 14-byte BMP
    file header); the extractor rebuilds the file header itself.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), (255, 0, 0)).save(buffer, "BMP")
    info_header = buffer.getvalue()[14:]

    table_offset = 0x40
    image_start = 0x200
    data = bytearray(image_start + len(info_header))
    data[0:6] = b"AC1015"
    struct.pack_into("<i", data, 0x0D, table_offset - 0x14)
    data[table_offset] = 1
    struct.pack_into("<B", data, table_offset + 1, 2)
    struct.pack_into("<ii", data, table_offset + 2, image_start, len(info_header))
    data[image_start:] = info_header
    path.write_bytes(data)


def test_dwg_with_one_preview_record_is_accepted(tmp_path):
    from previewgen.renderers.cad import extract_dwg_thumbnail

    path = tmp_path / "single-record.dwg"
    _write_single_record_dwg(path)

    thumbnail = extract_dwg_thumbnail(path)

    assert thumbnail is not None
    assert thumbnail.size == (8, 6)
    assert thumbnail.getpixel((1, 1)) == (255, 0, 0, 255)


def test_dwg_with_zero_preview_records_is_rejected(tmp_path):
    from previewgen.renderers.cad import extract_dwg_thumbnail

    path = tmp_path / "no-records.dwg"
    _write_single_record_dwg(path)
    data = bytearray(path.read_bytes())
    data[0x40] = 0
    path.write_bytes(data)

    assert extract_dwg_thumbnail(path) is None


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [(".iges", "IGES"), (".igs", "IGES"), (".step", "STEP"), (".stp", "STEP")],
)
def test_cad_solid_selects_reader_from_extension(monkeypatch, tmp_path, suffix, expected):
    cascadio = pytest.importorskip("cascadio")
    trimesh = pytest.importorskip("trimesh")

    from previewgen.config import PreviewConfig
    from previewgen.renderers import cad

    glb = trimesh.creation.box().export(file_type="glb")
    selected: list[object] = []

    def fake_to_glb(data, file_type=None):
        selected.append(file_type)
        return glb

    monkeypatch.setattr(cascadio, "to_glb_bytes", fake_to_glb)

    marker = Image.new("RGBA", (16, 16), (0, 0, 0, 255))
    render_calls: list[dict] = []

    def fake_render(**kwargs):
        render_calls.append(kwargs)
        return marker

    monkeypatch.setattr(cad, "render_3d_mesh", fake_render)

    source = tmp_path / f"solid{suffix}"
    source.write_bytes(b"CAD payload")

    result = cad._load_cad_solid(source, PreviewConfig(), target_dimension=64)

    assert result is marker
    assert selected == [getattr(cascadio.FileType, expected)]
    assert render_calls and render_calls[0]["z_up"] is True
