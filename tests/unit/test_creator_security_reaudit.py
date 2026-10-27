"""Source-level regressions for Krita, nested brushes and Maya previews."""
from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from previewgen import config
from previewgen.renderers.creator import _load_kra, _load_procreate_brush
from previewgen.renderers.proprietary import extract_maya_thumbnail

pytestmark = pytest.mark.core


def _png(color=(70, 120, 170, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (32, 32), color).save(buf, format="PNG")
    return buf.getvalue()


def test_krita_case_insensitive_nested_preview(tmp_path: Path):
    source = tmp_path / "art.kra"
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("PREVIEWS/MergedImage.PNG", _png())
    assert _load_kra(source).size == (32, 32)


def test_krita_missing_preview_reports_meaningful_failure(tmp_path: Path):
    source = tmp_path / "missing.kra"
    with zipfile.ZipFile(source, "w") as zf:
        zf.writestr("maindoc.xml", "<DOC/>")
    with pytest.raises(RuntimeError, match="No Krita mergedimage.png or preview.png"):
        _load_kra(source)


def test_nested_procreate_brush_preview(tmp_path: Path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as inner:
        inner.writestr("QuickLook/Thumbnail.png", _png())
    source = tmp_path / "set.brushset"
    with zipfile.ZipFile(source, "w") as outer:
        outer.writestr("Brushes/first.brush", buffer.getvalue())
    assert _load_procreate_brush(source).size == (32, 32)


def test_nested_brush_rejects_oversized_central_directory(tmp_path: Path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as inner:
        for index in range(config.MAX_ZIP_MEMBERS + 1):
            inner.writestr(f"item-{index}.txt", b"")
    source = tmp_path / "malicious.brushset"
    with zipfile.ZipFile(source, "w") as outer:
        outer.writestr("payload.brush", buffer.getvalue())
    with pytest.raises(RuntimeError, match="exceeds maximum member limit"):
        _load_procreate_brush(source)


def test_maya_ascii_multiline_thumbnail_after_long_geometry_line(tmp_path: Path):
    data = base64.b64encode(_png()).decode("ascii")
    parts = [data[i:i+32] for i in range(0, len(data), 32)]
    source = tmp_path / "scene.ma"
    source.write_text(
        "setAttr .points -type string " + "x" * 200_000 + ";\n"
        + "thumbnail\n" + "\n".join(f'"{part}"' for part in parts),
        encoding="utf-8",
    )
    image = extract_maya_thumbnail(source)
    assert image is not None
    assert image.size == (32, 32)
