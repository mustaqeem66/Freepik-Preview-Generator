"""
PreviewGen Creator Software Loaders
Extracts full-resolution preview buffers from digital illustration and design software:
Procreate (.procreate, .brush, .brushset), Clip Studio Paint (.clip), Krita (.kra),
Affinity Suite (.afdesign, .afphoto, .afpub), InDesign (.indd), and Photoshop Brushes (.abr).
"""
from __future__ import annotations

import base64
import contextlib
import io
import math
import re
import sqlite3
import struct
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

from previewgen import config as previewgen_config
from previewgen import limits


def _archive_image(zf: zipfile.ZipFile, name: str, nested: bool = False) -> Image.Image:
    member = zf.getinfo(name)
    if len(zf.infolist()) > previewgen_config.MAX_ZIP_MEMBERS:
        raise ValueError("Archive exceeds maximum member count")
    if member.file_size > previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES:
        raise ValueError("Embedded image exceeds size limit")
    ratio_limit = member.compress_size * previewgen_config.MAX_COMPRESSION_RATIO
    if member.file_size > 1_000_000 and member.file_size > ratio_limit:
        raise ValueError("Embedded image exceeds compression ratio limit")
    with zf.open(member) as stream:
        data = stream.read(previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES + 1)
    if len(data) > previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES:
        raise ValueError("Embedded image exceeds size limit")
    if name.lower().endswith(".brush") and not nested:
        # Inspect the *inner* central directory before ZipFile creates ZipInfo
        # objects. A brushset can contain a zip bomb disguised as one brush.
        with tempfile.TemporaryDirectory(prefix="previewgen_nested_brush_") as root:
            inner_path = Path(root) / "inner.brush"
            inner_path.write_bytes(data)
            with limits.open_zip_bounded(
                inner_path, max_entries=previewgen_config.MAX_ZIP_MEMBERS
            ) as brush:
                names = brush.namelist()
                target = next((n for n in names if n.lower().endswith("thumbnail.png")), None)
                target = target or next((n for n in names if n.lower().endswith("shape.png")), None)
                if not target:
                    raise ValueError("No image in nested Procreate brush")
                return _archive_image(brush, target, nested=True)
    image = limits.bounded_image_from_bytes(data, name)
    if Path(name).name.lower() == "shape.png":
        alpha = image.convert("L")
        image = Image.new("RGBA", image.size, (30, 30, 35, 255))
        image.putalpha(alpha)
    return image


def _load_procreate(source_path: Path) -> Image.Image:
    """Extract flattened canvas composite from a Procreate (.procreate) document."""
    try:
        with limits.open_zip_bounded(source_path) as zf:
            names = zf.namelist()
            target = next(
                (n for n in names if n.lower() in ("quicklook/thumbnail.png", "thumbnail.png")),
                None,
            )
            if not target:
                raise ValueError("No QuickLook/Thumbnail.png found in .procreate archive")
            return _archive_image(zf, target)
    except Exception as exc:
        raise RuntimeError(f"Could not load Procreate artwork '{source_path.name}': {exc}") from exc


def _load_procreate_brush(source_path: Path) -> Image.Image:
    """Extract brush tip or stroke preview from .brush or .brushset."""
    try:
        with limits.open_zip_bounded(source_path) as zf:
            names = zf.namelist()
            # 1. Prefer QuickLook preview
            target = next(
                (n for n in names if "thumbnail.png" in n.lower()),
                None,
            )
            # 2. Fall back to shape mask
            if not target:
                target = next((n for n in names if "shape.png" in n.lower()), None)
            if not target:
                target = next((n for n in names if n.lower().endswith(".brush")), None)

            if not target:
                raise ValueError("No thumbnail or shape mask found in Procreate brush archive")
            return _archive_image(zf, target)
    except Exception as exc:
        raise RuntimeError(f"Could not load Procreate brush '{source_path.name}': {exc}") from exc


def _load_brushset_contact_sheet(
    source_path: Path, target_dimension: int = 900
) -> Image.Image:
    """Opt-in preview of up to nine nested Procreate brush tips.

    Every nested .brush passes through the existing bounded ZIP reader. One
    invalid nested brush causes an explicit failure, not a misleading partial
    success. No extra files are read beyond the selected outer .brushset.
    """
    from PIL import ImageDraw

    dimension = max(240, min(2400, int(target_dimension)))
    try:
        with limits.open_zip_bounded(source_path) as archive:
            names = sorted(
                (name for name in archive.namelist() if name.lower().endswith(".brush")),
                key=str.lower,
            )
            if not names:
                raise ValueError("Brushset has no nested .brush tip archives")
            # Limit both decoder count and temporary image allocations to nine.
            tips = [_archive_image(archive, name) for name in names[:9]]
    except Exception as exc:
        raise RuntimeError(
            f"Could not build brushset contact sheet for '{source_path.name}': {exc}"
        ) from exc

    columns = min(3, math.ceil(math.sqrt(len(tips))))
    rows = (len(tips) + columns - 1) // columns
    sheet = Image.new("RGBA", (dimension, dimension), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    for index, tip in enumerate(tips):
        col = index % columns
        row = index // columns
        x0 = col * dimension // columns
        x1 = (col + 1) * dimension // columns
        y0 = row * dimension // rows
        y1 = (row + 1) * dimension // rows
        cell_w, cell_h = x1 - x0, y1 - y0
        pad = max(2, min(cell_w, cell_h) // 24)
        tile = tip.convert("RGBA")
        tile.thumbnail(
            (max(1, cell_w - 2 * pad), max(1, cell_h - 2 * pad)),
            Image.Resampling.LANCZOS,
        )
        dx = x0 + (cell_w - tile.width) // 2
        dy = y0 + (cell_h - tile.height) // 2
        sheet.alpha_composite(tile, (dx, dy))
        if cell_w > 4 and cell_h > 4:
            draw.rectangle(
                (x0, y0, x1 - 1, y1 - 1),
                outline=(130, 145, 160, 190), width=1,
            )
    return sheet


def _load_clip(source_path: Path) -> Image.Image:
    """Extract canvas preview from a Clip Studio Paint (.clip) SQLite container."""
    try:
        with open(source_path, "rb") as stream:
            header = stream.read(24)
            database = None
            if header.startswith(b"CSFCHUNK"):
                _, head_offset = struct.unpack(">QQ", header[8:24])
                stream.seek(head_offset)
                head = stream.read(32)
                if head[:8] != b"CHNKHead":
                    raise ValueError("Invalid CLIP header chunk")
                sql_offset = struct.unpack_from(">Q", head, 24)[0]
                stream.seek(sql_offset)
                chunk = stream.read(16)
                if chunk[:8] != b"CHNKSQLi":
                    raise ValueError("Missing CLIP database chunk")
                length = struct.unpack(">Q", chunk[8:])[0]
                if length > previewgen_config.MAX_MEMBER_BYTES:
                    raise ValueError("CLIP database exceeds size limit")
                database = stream.read(length)
                if len(database) != length:
                    raise ValueError("Truncated CLIP database")
            elif not header.startswith(b"SQLite format 3\x00"):
                raise ValueError("Unsupported CLIP container")
        uri = ":memory:" if database is not None else source_path.resolve().as_uri() + "?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=database is None, timeout=5.0)) as conn:
            if database is not None:
                conn.deserialize(database)
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES)
            row = conn.execute("SELECT ImageData FROM CanvasPreview LIMIT 1").fetchone()
            if not row or not row[0]:
                raise ValueError("CanvasPreview table has no preview image data")
            return limits.bounded_image_from_bytes(row[0], "CLIP preview")
    except Exception as exc:
        raise RuntimeError(f"Could not load Clip Studio Paint file '{source_path.name}': {exc}") from exc


def _load_kra(source_path: Path) -> Image.Image:
    """Extract flattened composite or preview from a Krita (.kra) OpenDocument ZIP."""
    try:
        with limits.open_zip_bounded(source_path) as zf:
            names = zf.namelist()
            # Some valid archives use different casing or place previews
            # inside subfolders. Never assume preview.png exists.
            target = next(
                (name for expected in ("mergedimage.png", "preview.png")
                 for name in names if name.rsplit("/", 1)[-1].lower() == expected),
                None,
            )
            if target is None:
                raise ValueError("No Krita mergedimage.png or preview.png available")
            return _archive_image(zf, target)
    except Exception as exc:
        raise RuntimeError(f"Could not load Krita painting '{source_path.name}': {exc}") from exc


def _load_affinity(source_path: Path) -> Image.Image:
    """Extract embedded PNG preview chunk from Affinity Designer/Photo/Publisher files."""
    try:
        # Scan binary header (bounded to first 16 MB)
        with open(source_path, "rb") as f:
            header_bytes = f.read(16 * 1024 * 1024)

        png_sig = b"\x89PNG\r\n\x1a\n"
        start_idx = header_bytes.find(png_sig)
        if start_idx == -1:
            raise ValueError("No embedded PNG preview signature found in Affinity file")

        iend_sig = b"IEND\xaeB\x60\x82"
        end_idx = header_bytes.find(iend_sig, start_idx)
        if end_idx == -1:
            raise ValueError("Corrupt embedded PNG preview: missing IEND chunk")

        png_data = header_bytes[start_idx : end_idx + len(iend_sig)]
        return limits.bounded_image_from_bytes(png_data, "Affinity preview")
    except Exception as exc:
        raise RuntimeError(f"Could not load Affinity document '{source_path.name}': {exc}") from exc


def _load_indd(source_path: Path) -> Image.Image:
    """Extract spread preview JPEG from an Adobe InDesign (.indd) XMP metadata packet."""
    try:
        with open(source_path, "rb") as f:
            data = f.read(2 * 1024 * 1024)  # Search in first 2 MB

        match = re.search(rb"<xmpGImg:image>([^<]+)</xmpGImg:image>", data)
        if not match:
            # Fallback: scan footer (last 1 MB) where some InDesign versions place XMP
            file_size = source_path.stat().st_size
            if file_size > 2 * 1024 * 1024:
                with open(source_path, "rb") as f:
                    f.seek(max(0, file_size - 1024 * 1024))
                    data = f.read()
                match = re.search(rb"<xmpGImg:image>([^<]+)</xmpGImg:image>", data)

        if not match:
            raise ValueError("No embedded XMP thumbnail (<xmpGImg:image>) found in InDesign document")

        b64_clean = re.sub(rb"\s+", b"", match.group(1))
        jpeg_bytes = base64.b64decode(b64_clean)
        return limits.bounded_image_from_bytes(jpeg_bytes, "InDesign preview")
    except Exception as exc:
        raise RuntimeError(f"Could not load InDesign preview for '{source_path.name}': {exc}") from exc


def _brush_tip(record: bytes) -> Image.Image:
    top, left, bottom, right, depth, compression = struct.unpack_from(">iiiiHB", record)
    width, height = right - left, bottom - top
    limits.check_raster_size(width, height, "ABR brush")
    if depth not in (8, 16):
        raise ValueError("Unsupported ABR sample depth")
    row_bytes = width * (depth // 8)
    expected = row_bytes * height
    if expected > previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES:
        raise ValueError("ABR sample exceeds size limit")
    payload = memoryview(record)[19:]
    if compression == 0:
        pixels = bytes(payload[:expected])
    elif compression == 1:
        lengths = struct.unpack_from(f">{height}H", payload)
        offset = height * 2
        pixels = bytearray()
        for length in lengths:
            end = offset + length
            if end > len(payload):
                raise ValueError("Truncated ABR compressed row")
            row = bytearray()
            while offset < end:
                control = payload[offset]
                offset += 1
                if control < 128:
                    count = control + 1
                    if offset + count > end:
                        raise ValueError("Truncated ABR literal")
                    row.extend(payload[offset:offset + count])
                    offset += count
                elif control > 128:
                    if offset >= end:
                        raise ValueError("Truncated ABR repeat")
                    row.extend(bytes([payload[offset]]) * (257 - control))
                    offset += 1
                if len(row) > row_bytes:
                    raise ValueError("ABR compressed row exceeds declared width")
            if len(row) != row_bytes:
                raise ValueError("ABR compressed row has incorrect width")
            pixels.extend(row)
    else:
        raise ValueError("Unsupported ABR compression")
    if len(pixels) != expected:
        raise ValueError("Truncated ABR sample")
    alpha = Image.frombytes("L", (width, height), bytes(pixels[::2] if depth == 16 else pixels))
    image = Image.new("RGBA", (width, height), (30, 30, 35, 255))
    image.putalpha(alpha)
    return image


def _load_abr(source_path: Path) -> Image.Image:
    """Decode the first sampled tip in legacy or tagged ABR containers."""
    try:
        data = source_path.read_bytes()
        version, secondary = struct.unpack_from(">HH", data)
        offset = 4
        if version in (1, 2):
            for _ in range(secondary):
                kind, length = struct.unpack_from(">HI", data, offset)
                offset += 6
                end = offset + length
                if end > len(data):
                    raise ValueError("Truncated ABR brush record")
                record = data[offset:end]
                offset = end
                if kind != 2:
                    continue
                position = 6  # miscellaneous value and spacing
                if version == 2:
                    name_length = struct.unpack_from(">I", record, position)[0]
                    position += 4 + name_length * 2
                position += 9  # antialias flag and short bounds
                return _brush_tip(record[position:])
        elif version in (6, 7, 9, 10) and secondary in (1, 2):
            while offset + 12 <= len(data):
                signature, tag, length = struct.unpack_from(">4s4sI", data, offset)
                offset += 12
                end = offset + length
                if signature != b"8BIM" or end > len(data):
                    raise ValueError("Invalid ABR tagged block")
                if tag == b"samp" and length:
                    sample_length = struct.unpack_from(">I", data, offset)[0]
                    start = offset + 4
                    sample_end = start + sample_length
                    if sample_end > end:
                        raise ValueError("Truncated ABR sampled brush")
                    name_length = data[start]
                    start += 1 + name_length + (10 if secondary == 1 else 264)
                    return _brush_tip(data[start:sample_end])
                offset = end + (-length % 4)
        raise ValueError("No supported sampled brush data found; computed brushes are not raster samples")
    except Exception as exc:
        raise RuntimeError(f"Could not load Photoshop brush '{source_path.name}': {exc}") from exc
