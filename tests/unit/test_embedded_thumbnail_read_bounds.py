"""Pre-read bounds for embedded OLE/AutoCAD thumbnails."""
from __future__ import annotations

import io
import struct
import sys
import types
from pathlib import Path

from PIL import Image
import pytest

from previewgen.config import MAX_EMBEDDED_THUMBNAIL_BYTES
from previewgen.renderers.cad import extract_dwg_thumbnail
from previewgen.renderers.proprietary import extract_max_thumbnail

pytestmark = pytest.mark.core


def _png() -> bytes:
    image = Image.new("RGBA", (12, 16), (40, 90, 130, 255))
    buff = io.BytesIO()
    image.save(buff, format="PNG")
    return buff.getvalue()


def test_ole_oversized_thumbnail_is_not_opened_even_if_stream_exists(monkeypatch):
    png = _png()

    class TestOle:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def listdir(self): return [["thumbnail_oversized"], ["thumbnail_safe"]]
        def get_size(self, path):
            return MAX_EMBEDDED_THUMBNAIL_BYTES + 1 if path[0] == "thumbnail_oversized" else len(png)
        def openstream(self, path):
            if path[0] != "thumbnail_safe":
                raise AssertionError("Overlarge OLE stream must never be opened")
            return io.BytesIO(png)
        def exists(self, name): return False

    module = types.SimpleNamespace(
        isOleFile=lambda _: True,
        OleFileIO=lambda _: TestOle(),
    )
    monkeypatch.setitem(sys.modules, "olefile", module)
    result = extract_max_thumbnail(Path("not-a-real-file.max"))
    assert result is not None
    assert result.size == (12, 16)


def test_ole_stream_read_request_is_capped_even_when_directory_reports_small(monkeypatch):
    requests = []

    class Stream:
        def read(self, limit=-1):
            requests.append(limit)
            if limit > MAX_EMBEDDED_THUMBNAIL_BYTES + 1 or limit < 0:
                raise AssertionError("Unbounded or oversized read")
            return b"not-a-thumbnail"

    class Ole:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def listdir(self): return [["thumbnail"]]
        def get_size(self, name): return 10
        def openstream(self, name): return Stream()
        def exists(self, name): return False

    monkeypatch.setitem(sys.modules, "olefile", types.SimpleNamespace(
        isOleFile=lambda _: True, OleFileIO=lambda _: Ole(),
    ))
    assert extract_max_thumbnail(Path("fake.max")) is None
    assert requests == [MAX_EMBEDDED_THUMBNAIL_BYTES + 1]


def _dwg_with_entry(path: Path, png: bytes | None, declared_size: int) -> None:
    start = 96
    with path.open("wb") as stream:
        stream.write(b"AC1027")
        stream.seek(0x0D)
        stream.write(struct.pack("<i", 0))  # directory at 0x14
        stream.seek(0x14)
        stream.write(bytes([1, 6]))
        stream.write(struct.pack("<ii", start, declared_size))
        if png is not None:
            stream.seek(start)
            stream.write(png)
        else:
            # Sparse extent makes the directory plausible without allocating
            # hundreds of megabytes in the test environment.
            stream.truncate(start + declared_size + 1)


def test_dwg_refuses_embedded_png_larger_than_declared_thumbnail_limit(tmp_path: Path):
    path = tmp_path / "overlarge.dwg"
    _dwg_with_entry(path, None, MAX_EMBEDDED_THUMBNAIL_BYTES + 1)
    assert extract_dwg_thumbnail(path) is None


def test_dwg_still_loads_small_valid_png(tmp_path: Path):
    path = tmp_path / "good.dwg"
    png = _png()
    _dwg_with_entry(path, png, len(png))
    thumb = extract_dwg_thumbnail(path)
    assert thumb is not None
    assert thumb.size == (12, 16)
