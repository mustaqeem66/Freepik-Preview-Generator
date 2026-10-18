"""
Tests for Creator and Vector Format Loaders:
Procreate (.procreate, .brush, .brushset), Clip Studio Paint (.clip), Krita (.kra),
Affinity Suite (.afdesign, .afphoto, .afpub), InDesign (.indd), Photoshop Brushes (.abr),
Illustrator (.ai), PostScript (.eps), and Typography Fonts (.ttf, .otf).
"""
from __future__ import annotations

import base64
import io
import sqlite3
import struct
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from previewgen.renderers import generate_file
from previewgen.renderers.creator import (
    _load_abr,
    _load_affinity,
    _load_clip,
    _load_indd,
    _load_kra,
    _load_procreate,
    _load_procreate_brush,
)
from previewgen.renderers.vector import _load_ai, _load_eps
from processor import PreviewConfig

pytestmark = pytest.mark.core


def test_load_procreate(tmp_path: Path) -> None:
    """Verify full-canvas composite extraction from .procreate ZIP container."""
    doc = tmp_path / "illustration.procreate"
    img = Image.new("RGBA", (200, 200), (255, 120, 40, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with zipfile.ZipFile(doc, "w") as zf:
        zf.writestr("Document.archive", b"plist_mock_data")
        zf.writestr("QuickLook/Thumbnail.png", buf.getvalue())

    loaded = _load_procreate(doc)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (200, 200)
    assert loaded.mode == "RGBA"


def test_load_procreate_brush(tmp_path: Path) -> None:
    """Verify brush tip extraction from .brush and .brushset ZIP container."""
    brush_file = tmp_path / "pencil.brush"
    img = Image.new("RGBA", (128, 128), (50, 150, 250, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with zipfile.ZipFile(brush_file, "w") as zf:
        zf.writestr("QuickLook/Thumbnail.png", buf.getvalue())

    loaded = _load_procreate_brush(brush_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (128, 128)
    assert loaded.mode == "RGBA"


def test_load_clip(tmp_path: Path) -> None:
    """Verify canvas preview extraction from Clip Studio Paint (.clip) SQLite database."""
    clip_file = tmp_path / "manga.clip"
    img = Image.new("RGBA", (240, 320), (30, 80, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with sqlite3.connect(clip_file) as conn:
        conn.execute("CREATE TABLE CanvasPreview (ImageData BLOB, ImageWidth INTEGER, ImageHeight INTEGER);")
        conn.execute("INSERT INTO CanvasPreview VALUES (?, 240, 320);", (buf.getvalue(),))
        conn.commit()

    loaded = _load_clip(clip_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (240, 320)
    assert loaded.mode == "RGBA"


def test_load_kra(tmp_path: Path) -> None:
    """Verify flattened composite extraction from Krita (.kra) ZIP container."""
    kra_file = tmp_path / "artwork.kra"
    img = Image.new("RGBA", (300, 300), (80, 220, 100, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    with zipfile.ZipFile(kra_file, "w") as zf:
        zf.writestr("mergedimage.png", buf.getvalue())
        zf.writestr("preview.png", buf.getvalue())

    loaded = _load_kra(kra_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (300, 300)
    assert loaded.mode == "RGBA"


def test_load_affinity(tmp_path: Path) -> None:
    """Verify embedded PNG chunk extraction from Affinity Designer (.afdesign)."""
    af_file = tmp_path / "vector.afdesign"
    img = Image.new("RGBA", (180, 180), (220, 40, 160, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # Prepend mock Affinity header and append mock blocks
    raw_content = b"AFFINITY_V2_MOCK_HEADER_DATA" + png_bytes + b"EXTRA_CHUNKS"
    af_file.write_bytes(raw_content)

    loaded = _load_affinity(af_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (180, 180)
    assert loaded.mode == "RGBA"


def test_load_indd(tmp_path: Path) -> None:
    """Verify spread preview JPEG extraction from InDesign (.indd) XMP metadata."""
    indd_file = tmp_path / "brochure.indd"
    img = Image.new("RGB", (160, 200), (200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")

    xmp_mock = (
        b"INDESIGN_BINARY_START<?xpacket begin=''?><x:xmpmeta><xmpGImg:image>"
        + b64_str.encode("ascii")
        + b"</xmpGImg:image></x:xmpmeta><?xpacket end='w'?>INDESIGN_BINARY_END"
    )
    indd_file.write_bytes(xmp_mock)

    loaded = _load_indd(indd_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (160, 200)
    assert loaded.mode == "RGBA"


def test_load_abr(tmp_path: Path) -> None:
    """Verify brush tip alpha stamp parsing from Photoshop (.abr) file."""
    abr_file = tmp_path / "ink.abr"
    w, h = 48, 48
    header = struct.pack(">HH", 1, 1)  # Version 1, 1 brush
    bounds = struct.pack(">IHB4h4iHB", 0, 25, 1, 0, 0, h, w, 0, 0, h, w, 8, 0)
    raw_pixels = bytes([i % 256 for i in range(w * h)])
    abr_data = header + struct.pack(">HI", 2, len(bounds) + len(raw_pixels)) + bounds + raw_pixels
    abr_file.write_bytes(abr_data)

    loaded = _load_abr(abr_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (w, h)
    assert loaded.mode == "RGBA"
    assert loaded.getchannel("A").tobytes() == raw_pixels


def test_load_eps_dos_binary(tmp_path: Path) -> None:
    """Verify DOS EPS binary header TIFF thumbnail slice extraction."""
    eps_file = tmp_path / "icon.eps"
    tiff_img = Image.new("RGBA", (140, 140), (255, 180, 0, 255))
    t_buf = io.BytesIO()
    tiff_img.save(t_buf, format="TIFF")
    tiff_bytes = t_buf.getvalue()

    ps_code = b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 140 140\n"
    ps_offset = 30
    ps_len = len(ps_code)
    tiff_offset = ps_offset + ps_len
    tiff_len = len(tiff_bytes)

    header = struct.pack("<LLLLLLLH", 0xC6D3D0C5, ps_offset, ps_len, 0, 0, tiff_offset, tiff_len, 0xFFFF)
    eps_file.write_bytes(header + ps_code + tiff_bytes)

    loaded = _load_eps(eps_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (140, 140)
    assert loaded.mode == "RGBA"


def test_load_ai_xmp_fallback(tmp_path: Path) -> None:
    """Verify Adobe Illustrator (.ai) XMP thumbnail fallback extraction."""
    ai_file = tmp_path / "logo.ai"
    img = Image.new("RGB", (150, 150), (10, 150, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")

    ai_data = b"%!PS-Adobe-3.0\n<xmpGImg:image>" + b64_str.encode("ascii") + b"</xmpGImg:image>\n%%EOF"
    ai_file.write_bytes(ai_data)

    loaded = _load_ai(ai_file)
    assert isinstance(loaded, Image.Image)
    assert loaded.size == (150, 150)
    assert loaded.mode == "RGBA"




def test_generate_file_end_to_end_creator_formats(tmp_path: Path) -> None:
    """Verify end-to-end generate_file compositing over diagonal split for all new formats."""
    # 1. Procreate
    procreate_src = tmp_path / "test.procreate"
    img = Image.new("RGBA", (200, 200), (255, 50, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with zipfile.ZipFile(procreate_src, "w") as zf:
        zf.writestr("QuickLook/Thumbnail.png", buf.getvalue())

    out_jpg = tmp_path / "procreate_preview.jpg"
    generate_file(procreate_src, out_jpg, PreviewConfig(text="PROCREATE PREVIEW"))
    assert out_jpg.is_file() and out_jpg.stat().st_size > 0
    with Image.open(out_jpg) as out:
        assert out.format == "JPEG"

    # 2. Clip Studio Paint
    clip_src = tmp_path / "test.clip"
    with sqlite3.connect(clip_src) as conn:
        conn.execute("CREATE TABLE CanvasPreview (ImageData BLOB, ImageWidth INTEGER, ImageHeight INTEGER);")
        conn.execute("INSERT INTO CanvasPreview VALUES (?, 200, 200);", (buf.getvalue(),))
        conn.commit()

    clip_out = tmp_path / "clip_preview.jpg"
    generate_file(clip_src, clip_out, PreviewConfig(text="CLIP STUDIO"))
    assert clip_out.is_file() and clip_out.stat().st_size > 0
