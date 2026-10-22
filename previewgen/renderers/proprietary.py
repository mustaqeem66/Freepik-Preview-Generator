"""
PreviewGen Proprietary Format Renderers
Extracts embedded preview thumbnails from formats that have no open source
geometry loader: Autodesk 3ds Max (.max), Fusion 360 (.f3d), Maya (.mb/.ma),
and Blender (.blend).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from previewgen import config as previewgen_config
from previewgen import limits

# Accepted BMP DIB header sizes (BITMAPCOREHEADER and the later info headers).
_BMP_INFO_SIZES = {12, 40, 52, 56, 108, 124}


def _find_embedded_bmp(data: bytes) -> bytes | None:
    """Return a plausible embedded BMP, or ``None``.

    ``b"BM"`` on its own matches plenty of unrelated bytes inside an OLE
    stream, and handing that slice to the decoder either fails or invents a
    garbage thumbnail, so the header fields have to agree before use.
    """
    start = 0
    while True:
        idx = data.find(b"BM", start)
        if idx < 0:
            return None
        start = idx + 2
        header = data[idx:idx + 54]
        if len(header) < 54:
            continue
        file_size = int.from_bytes(header[2:6], "little")
        reserved = int.from_bytes(header[6:10], "little")
        pixel_offset = int.from_bytes(header[10:14], "little")
        info_size = int.from_bytes(header[14:18], "little")
        width = int.from_bytes(header[18:22], "little", signed=True)
        height = int.from_bytes(header[22:26], "little", signed=True)
        if reserved != 0 or info_size not in _BMP_INFO_SIZES:
            continue
        if not 0 < file_size <= len(data) - idx or not 14 <= pixel_offset < file_size:
            continue
        max_dim = previewgen_config.MAX_RASTER_DIMENSION
        if width == 0 or height == 0 or abs(width) > max_dim or abs(height) > max_dim:
            continue
        return data[idx:idx + file_size]


def extract_max_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded viewport thumbnail from Autodesk 3ds Max (.max) OLE files."""
    try:
        import olefile
        if not olefile.isOleFile(str(path)):
            return None
        with olefile.OleFileIO(str(path)) as ole:
            for sname in ole.listdir():
                s_lower = "/".join(sname).lower()
                if "thumbnail" in s_lower or "preview" in s_lower:
                    data = ole.openstream(sname).read()
                    png_idx = data.find(b"\x89PNG\r\n\x1a\n")
                    if png_idx >= 0:
                        return limits.bounded_image_from_bytes(data[png_idx:], "3ds Max thumbnail")
                    bmp = _find_embedded_bmp(data)
                    if bmp is not None:
                        return limits.bounded_image_from_bytes(bmp, "3ds Max thumbnail")
            if ole.exists("\x05SummaryInformation"):
                stream = ole.openstream("\x05SummaryInformation").read()
                png_idx = stream.find(b"\x89PNG\r\n\x1a\n")
                if png_idx >= 0:
                    return limits.bounded_image_from_bytes(stream[png_idx:], "3ds Max thumbnail")
                bmp = _find_embedded_bmp(stream)
                if bmp is not None:
                    return limits.bounded_image_from_bytes(bmp, "3ds Max thumbnail")
        return None
    except Exception:
        return None


def _load_max(source_path: Path) -> Image.Image:
    thumb = extract_max_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError(
        "This 3ds Max file has no embedded viewport thumbnail. "
        "In 3ds Max, enable 'Save Preview' in File Preferences, or export to .obj / .glb."
    )


def extract_f3d_thumbnail(path: Path) -> Image.Image | None:
    """Extract pre-rendered high-res PNG thumbnail from Autodesk Fusion 360 (.f3d) archives."""
    import zipfile
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            for name in zf.namelist():
                if "thumbnail" in name.lower() and name.lower().endswith((".png", ".jpg", ".jpeg")):
                    if zf.getinfo(name).file_size > previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES:
                        # Keep looking: Fusion archives often carry a second,
                        # smaller preview alongside an oversized one.
                        continue
                    data = zf.read(name)
                    return limits.bounded_image_from_bytes(data, "Fusion 360 thumbnail")
        return None
    except Exception:
        return None


def _load_f3d(source_path: Path) -> Image.Image:
    thumb = extract_f3d_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError("Could not find embedded preview thumbnail in this Fusion 360 (.f3d) file.")


def extract_maya_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded swatch/thumbnail from Autodesk Maya (.mb, .ma) files."""
    try:
        ext = path.suffix.lower()
        if ext == ".ma":
            with open(path, encoding="utf-8", errors="ignore") as f:
                for _ in range(500):
                    line = f.readline()
                    if not line:
                        break
                    if "thumbnail" in line.lower():
                        import base64
                        import re
                        m = re.search(r'["\']([A-Za-z0-9+/=]{100,})["\']', line)
                        if m:
                            try:
                                 raw = base64.b64decode(m.group(1))
                                 return limits.bounded_image_from_bytes(raw, "Maya thumbnail")
                            except Exception:
                                pass
        elif ext == ".mb":
            with open(path, "rb") as f:
                header_data = f.read(512 * 1024)
                png_idx = header_data.find(b"\x89PNG\r\n\x1a\n")
                if png_idx >= 0:
                    return limits.bounded_image_from_bytes(header_data[png_idx:], "Maya thumbnail")
                jpg_idx = header_data.find(b"\xff\xd8\xff")
                if jpg_idx >= 0:
                    return limits.bounded_image_from_bytes(header_data[jpg_idx:], "Maya thumbnail")
        return None
    except Exception:
        return None


def _load_maya(source_path: Path) -> Image.Image:
    thumb = extract_maya_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError(
        "This Maya file has no embedded swatch thumbnail. "
        "In Maya, enable 'Save Thumbnail' in Scene Save Preferences, or export to .obj / .glb."
    )


def extract_blend_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded preview thumbnail from a .blend file in pure Python without Blender."""
    import gzip
    import struct

    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:2] == b"\x1f\x8b":
                f.seek(0)
                gf = gzip.GzipFile(fileobj=f)
                head = gf.read(12)
                stream = gf
            else:
                stream = f

            if not head.startswith(b"BLENDER"):
                return None

            is_64_bit = (head[7:8] == b"-")
            is_big_endian = (head[8:9] == b"V")
            sizeof_bhead = 24 if is_64_bit else 20
            int_endian = ">i" if is_big_endian else "<i"

            REND = b"REND"
            TEST = b"TEST"

            while True:
                bhead = stream.read(sizeof_bhead)
                if len(bhead) < sizeof_bhead:
                    return None
                code = bhead[:4]
                length = struct.unpack(int_endian, bhead[4:8])[0]
                if code == REND:
                    stream.seek(length, 1)
                else:
                    break

            if code != TEST:
                return None

            dims = stream.read(8)
            if len(dims) < 8:
                return None
            w, h = struct.unpack(int_endian + "i", dims)
            length -= 8
            if length != w * h * 4 or w <= 0 or h <= 0:
                return None
            if length > previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES:
                return None
            limits.check_raster_size(w, h, "Blender thumbnail")

            raw_rgba = stream.read(length)
            if len(raw_rgba) != length:
                return None

            img = Image.frombytes("RGBA", (w, h), raw_rgba)
            return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    except Exception:
        return None
