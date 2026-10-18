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
                    bmp_idx = data.find(b"BM")
                    if bmp_idx >= 0:
                        return limits.bounded_image_from_bytes(data[bmp_idx:], "3ds Max thumbnail")
            if ole.exists("\x05SummaryInformation"):
                stream = ole.openstream("\x05SummaryInformation").read()
                png_idx = stream.find(b"\x89PNG\r\n\x1a\n")
                if png_idx >= 0:
                    return limits.bounded_image_from_bytes(stream[png_idx:], "3ds Max thumbnail")
                bmp_idx = stream.find(b"BM")
                if bmp_idx >= 0:
                    return limits.bounded_image_from_bytes(stream[bmp_idx:], "3ds Max thumbnail")
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
                        return None
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
