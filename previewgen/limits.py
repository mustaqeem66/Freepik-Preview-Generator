"""
PreviewGen resource limits.

Every check here runs *before* the expensive parse/allocation step (header-only
reads, line/JSON scans) so that an oversized or hostile asset is rejected up
front instead of after it has already exhausted memory or disk. Failures raise
``ValueError`` whose message contains "exceed", which the error classifier maps
to ``CORRUPT_ASSET``; disk-space failures raise ``OSError(ENOSPC)`` mapped to
``DISK_FULL``.
"""
from __future__ import annotations

import contextlib
import errno
import json
import re
import shutil
import struct
import tempfile
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from previewgen import config as previewgen_config

RASTER_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".ico"}
)
SVG_EXTENSIONS = frozenset({".svg", ".svgz"})
MESH_EXTENSIONS = frozenset({".obj", ".stl", ".ply", ".glb", ".gltf"})
PSD_EXTENSIONS = frozenset({".psd"})


class ResourceInspectionError(ValueError):
    """Raised when resource limit inspection fails or cannot be validated."""


def _exceeds(message: str) -> None:
    raise ValueError(message)

def check_raster_size(width: int, height: int, label: str) -> None:
    if width <= 0 or height <= 0:
        _exceeds(f"{label} has no pixels")
    if (
        width > previewgen_config.MAX_RASTER_DIMENSION
        or height > previewgen_config.MAX_RASTER_DIMENSION
        or width * height > previewgen_config.MAX_IMAGE_PIXELS
    ):
        _exceeds(f"Raster dimensions {width}x{height} exceed the supported limit")


def compute_output_requirement(target_dimension: int = 2400) -> int:
    """Upper-bound the bytes a composed preview of ``target_dimension`` needs."""
    side = max(1, int(target_dimension))
    return side * side * 4


def check_output_size(width: int, height: int) -> None:
    """Reject an export size that exceeds the supported per-side cap.

    Validated before any allocation so a pathological request (e.g. upscaling a
    vector to 50000px) cannot exhaust memory.
    """
    if width <= 0 or height <= 0:
        _exceeds("Export size must be a positive pixel dimension")
    cap = previewgen_config.MAX_EXPORT_DIMENSION
    if width > cap or height > cap:
        _exceeds(f"Export size {width}x{height} exceeds the {cap}px per-side limit")


def ensure_free_disk_space(
    target_dir: Path | str,
    required_bytes: int,
    reserve_bytes: int | None = None,
) -> None:
    """Reject the render early if ``target_dir`` lacks room for the output."""
    reserve = previewgen_config.MIN_FREE_DISK_BYTES if reserve_bytes is None else reserve_bytes
    probe = Path(target_dir)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        return
    if free < required_bytes + reserve:
        raise OSError(
            errno.ENOSPC,
            f"Not enough free disk space at {probe} "
            f"({free // (1024 * 1024)} MB free, need "
            f"{(required_bytes + reserve) // (1024 * 1024)} MB)",
        )


def validate_raster_dimensions(source_path: Path | str) -> None:
    """Validate raster dimensions from the header without decoding pixels."""
    with Image.open(source_path) as img:
        width, height = img.size
    check_raster_size(width, height, Path(source_path).name)


_LENGTH_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([a-z%]*)\s*$", re.IGNORECASE)
_UNIT_SCALE: dict[str, float] = {
    "": 1.0,
    "px": 1.0,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
    "in": 96.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "q": 96.0 / 101.6,
    "em": 16.0,
    "ex": 8.0,
}


def _parse_length(value: str | None) -> float | None:
    if not value:
        return None
    match = _LENGTH_RE.match(value)
    if not match:
        return None
    unit = match.group(2).lower()
    if unit == "%":
        return None
    scale = _UNIT_SCALE.get(unit)
    if scale is None:
        return None
    return float(match.group(1)) * scale


def _declared_svg_size(text: str) -> tuple[float, float] | None:
    match = re.search(r"<svg\b[^>]*>", text[:131072], re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    tag = match.group(0)

    def attr(name: str) -> str | None:
        found = re.search(
            r"\b" + name + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", tag, re.IGNORECASE
        )
        if not found:
            return None
        return found.group(1) if found.group(1) is not None else found.group(2)

    width = _parse_length(attr("width"))
    height = _parse_length(attr("height"))
    if width and height and width > 0 and height > 0:
        return width, height

    view_box = attr("viewBox")
    if view_box:
        parts = re.split(r"[\s,]+", view_box.strip())
        if len(parts) == 4:
            try:
                vb_w, vb_h = float(parts[2]), float(parts[3])
            except ValueError:
                return None
            if vb_w > 0 and vb_h > 0:
                return vb_w, vb_h
    return None


def _gzip_decompress_limited(data: bytes, limit: int) -> bytes:
    obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = obj.decompress(data, limit + 1)
    if len(out) > limit:
        _exceeds(f"Compressed SVG expands beyond {limit // (1024 * 1024)} MB")
    return out


def _stream_gzip_text_limited(stream: Any, limit: int) -> str:
    """Stream-decompress a gzip stream, refusing output beyond ``limit`` bytes.

    Reads the source incrementally so a hostile ``.svgz`` cannot force the whole
    compressed file into memory before the expansion cap is applied.
    """
    obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        remaining = (limit + 1) - total
        out = obj.decompress(chunk, remaining if remaining > 0 else 0)
        chunks.append(out)
        total += len(out)
        if total > limit:
            _exceeds(f"Compressed SVG expands beyond {limit // (1024 * 1024)} MB")
        if obj.eof:
            break
    return b"".join(chunks).decode("utf-8", "replace")


# The SVG root tag (and its declared width/height/viewBox) lives at the very
# start of the document, so a bounded prefix is sufficient to validate it.
_SVG_HEADER_READ_BYTES = 256 * 1024


def validate_svg_limits(source_path: Path | str) -> None:
    """Validate the declared SVG size from a bounded prefix (never a full read)."""
    path = Path(source_path)
    size_bytes = path.stat().st_size
    if size_bytes > previewgen_config.MAX_SOURCE_FILE_BYTES:
        _exceeds(
            f"SVG source is {size_bytes // (1024 * 1024)} MB, beyond the "
            f"{previewgen_config.MAX_SOURCE_FILE_BYTES // (1024 * 1024)} MB limit"
        )
    with open(path, "rb") as stream:
        magic = stream.read(2)
        stream.seek(0)
        if magic == b"\x1f\x8b":
            text = _stream_gzip_text_limited(stream, previewgen_config.MAX_SVG_DECOMPRESSED_BYTES)
        else:
            text = stream.read(_SVG_HEADER_READ_BYTES).decode("utf-8", "replace")

    size = _declared_svg_size(text)
    if size is None:
        return
    width, height = size
    if (
        width > previewgen_config.MAX_SVG_DIMENSION
        or height > previewgen_config.MAX_SVG_DIMENSION
        or width * height > previewgen_config.MAX_IMAGE_PIXELS
    ):
        _exceeds(
            f"SVG declared size {int(width)}x{int(height)} exceeds the supported limit"
        )


def validate_psd_limits(source_path: Path | str) -> None:
    """Validate PSD canvas bounds and layer count before compositing."""
    from psd_tools import PSDImage

    psd = PSDImage.open(str(source_path))
    try:
        width, height = psd.width, psd.height
        if width <= 0 or height <= 0:
            _exceeds(f"{Path(source_path).name} has no pixels")
        if (
            width > previewgen_config.MAX_PSD_DIMENSION
            or height > previewgen_config.MAX_PSD_DIMENSION
            or width * height > previewgen_config.MAX_IMAGE_PIXELS
        ):
            _exceeds(f"PSD canvas {width}x{height} exceeds the supported limit")
        try:
            layer_count = sum(1 for _ in psd.descendants())
        except Exception:
            layer_count = len(psd)
        if layer_count > previewgen_config.MAX_PSD_LAYERS:
            _exceeds(
                f"PSD layer count {layer_count} exceeds the supported limit "
                f"({previewgen_config.MAX_PSD_LAYERS})"
            )
    finally:
        closer = getattr(psd, "close", None)
        if callable(closer):
            with contextlib.suppress(Exception):
                closer()


def _estimate_obj(path: Path) -> tuple[int, int]:
    faces = vertices = 0
    with open(path, "rb") as fh:
        for line in fh:
            if line[:2] == b"f ":
                faces += 1
            elif line[:2] == b"v ":
                vertices += 1
    return faces, vertices


def _estimate_stl(path: Path) -> tuple[int, int]:
    size = path.stat().st_size
    with open(path, "rb") as fh:
        header = fh.read(84)
    if len(header) >= 84:
        triangle_count = struct.unpack_from("<I", header, 80)[0]
        if triangle_count > 0 and 84 + triangle_count * 50 <= size + 2 and size > 200:
            return triangle_count, triangle_count * 3
    faces = 0
    with open(path, "rb") as fh:
        for line in fh:
            if line.lstrip()[:5] == b"facet":
                faces += 1
    return faces, faces * 3


def _estimate_ply(path: Path) -> tuple[int | None, int | None]:
    faces: int | None = None
    vertices: int | None = None
    with open(path, "rb") as fh:
        for _ in range(2000):
            line = fh.readline()
            if not line:
                break
            stripped = line.strip().lower()
            if stripped.startswith(b"element face"):
                with contextlib.suppress(ValueError):
                    faces = int(stripped.split()[-1])
            elif stripped.startswith(b"element vertex"):
                with contextlib.suppress(ValueError):
                    vertices = int(stripped.split()[-1])
            elif stripped == b"end_header":
                break
    return faces, vertices


def _count_gltf_faces(document: dict) -> tuple[int, int]:
    accessors = document.get("accessors") or []
    faces = 0
    vertices = 0

    def count_of(index: object) -> int:
        if isinstance(index, int) and 0 <= index < len(accessors):
            value = accessors[index].get("count")
            return int(value) if isinstance(value, (int, float)) else 0
        return 0

    for mesh in document.get("meshes") or []:
        for primitive in mesh.get("primitives") or []:
            indices = primitive.get("indices")
            if indices is not None:
                faces += count_of(indices) // 3
            else:
                position = (primitive.get("attributes") or {}).get("POSITION")
                position_count = count_of(position)
                vertices = max(vertices, position_count)
                faces += position_count // 3
    return faces, vertices


def _estimate_glb(path: Path) -> tuple[int | None, int | None]:
    with open(path, "rb") as fh:
        header = fh.read(12)
        if len(header) < 12:
            return None, None
        magic, _version, _length = struct.unpack("<4sII", header)
        if magic != b"glTF":
            return None, None
        while True:
            chunk_header = fh.read(8)
            if len(chunk_header) < 8:
                break
            chunk_length, chunk_type = struct.unpack("<I4s", chunk_header)
            payload = fh.read(chunk_length)
            if chunk_type == b"JSON":
                with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                    document = json.loads(payload.decode("utf-8", "replace"))
                    return _count_gltf_faces(document)
    return None, None


def estimate_mesh_complexity(source_path: Path | str) -> tuple[int | None, int | None]:
    """Return ``(faces, vertices)`` estimated from the file, or ``(None, None)``."""
    path = Path(source_path)
    ext = path.suffix.lower()
    if ext == ".obj":
        return _estimate_obj(path)
    if ext == ".stl":
        return _estimate_stl(path)
    if ext == ".ply":
        return _estimate_ply(path)
    if ext == ".glb":
        return _estimate_glb(path)
    if ext == ".gltf":
        with open(path, encoding="utf-8", errors="replace") as fh, contextlib.suppress(json.JSONDecodeError):
            return _count_gltf_faces(json.load(fh))
        return None, None
    return None, None


def validate_mesh_limits(source_path: Path | str) -> None:
    """Reject an oversized mesh from a cheap pre-parse complexity estimate."""
    faces, vertices = estimate_mesh_complexity(source_path)
    if faces is not None and faces > previewgen_config.MAX_3D_FACES:
        _exceeds(f"Mesh face count ~{faces} exceeds the supported limit")
    if vertices is not None and vertices > previewgen_config.MAX_3D_VERTICES:
        _exceeds(f"Mesh vertex count {vertices} exceeds the supported limit")


def validate_loaded_mesh(mesh: object) -> None:
    """Post-load guard for meshes whose complexity cannot be pre-estimated."""
    try:
        raw_faces = getattr(mesh, "faces", None)
        faces = len(raw_faces) if raw_faces is not None else 0
        raw_verts = getattr(mesh, "vertices", None)
        vertices = len(raw_verts) if raw_verts is not None else 0
    except (TypeError, AttributeError):
        return
    if faces > previewgen_config.MAX_3D_FACES:
        _exceeds(f"Mesh face count {faces} exceeds the supported limit")
    if vertices > previewgen_config.MAX_3D_VERTICES:
        _exceeds(f"Mesh vertex count {vertices} exceeds the supported limit")


def validate_dxf_entity_limits(document: object) -> None:
    """Reject a DXF whose modelspace has too many entities before drawing it."""
    try:
        count = len(document.modelspace())  # type: ignore[attr-defined]
    except Exception as exc:
        raise ResourceInspectionError(
            f"Failed to inspect DXF modelspace entity count: {exc}"
        ) from exc
    if count > previewgen_config.MAX_CAD_ENTITIES:
        _exceeds(f"CAD entity count {count} exceeds the supported limit")
def extract_zip_member_bounded(zf: Any, entry_name: str, dest_path: Path | str) -> None:
    """Copy a single archive member to ``dest_path`` enforcing member/ratio limits.

    Bounds both the declared and the actually-streamed byte count so a spoofed
    member header cannot force an unbounded expansion into the probe temp dir.
    """
    info = zf.getinfo(entry_name)
    if info.file_size > previewgen_config.MAX_MEMBER_BYTES:
        _exceeds(f"Archive member {entry_name} exceeds the supported member size")
    if info.compress_size > 0 and info.file_size / info.compress_size > previewgen_config.MAX_COMPRESSION_RATIO:
        _exceeds(f"Archive member {entry_name} exceeds the supported compression ratio")
    total = 0
    with zf.open(entry_name) as src, open(dest_path, "wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > previewgen_config.MAX_MEMBER_BYTES:
                _exceeds(f"Archive member {entry_name} exceeds the supported member size")
            dst.write(chunk)


def bounded_image_from_bytes(
    data: bytes,
    label: str,
    max_bytes: int | None = None,
) -> Image.Image:
    """Decode an embedded thumbnail from bounded bytes and bounds-checked size."""
    limit = previewgen_config.MAX_EMBEDDED_THUMBNAIL_BYTES if max_bytes is None else max_bytes
    if len(data) > limit:
        _exceeds(f"{label} exceeds the supported embedded size limit")
    with Image.open(BytesIO(data)) as img:
        width, height = img.size
        check_raster_size(width, height, label)
        img.load()
        # Embedded thumbnails are frequently JPEG, and JPEG orientation lives in
        # EXIF rather than in the pixel order; without this the preview is rotated.
        oriented = ImageOps.exif_transpose(img)
        return (oriented or img).convert("RGBA")


def validate_source_before_parse(source_path: Path | str) -> None:
    """Dispatch format-specific pre-parse limits for ``source_path``.

    Fails closed: for a supported format, if the asset cannot be inspected the
    call raises a typed :class:`ResourceInspectionError` instead of allowing an
    uninspected, untrusted payload to reach the parser.
    """
    path = Path(source_path)
    ext = path.suffix.lower()
    try:
        size_bytes = path.stat().st_size
    except OSError:
        size_bytes = 0
    if size_bytes > previewgen_config.MAX_SOURCE_FILE_BYTES:
        _exceeds(
            f"{path.name} is {size_bytes // (1024 * 1024)} MB, beyond the "
            f"{previewgen_config.MAX_SOURCE_FILE_BYTES // (1024 * 1024)} MB source limit"
        )
    try:
        if ext in RASTER_EXTENSIONS:
            validate_raster_dimensions(path)
        elif ext in SVG_EXTENSIONS:
            validate_svg_limits(path)
        elif ext == ".psd":
            validate_psd_limits(path)
        elif ext in MESH_EXTENSIONS:
            validate_mesh_limits(path)
    except ImportError:
        raise
    except (ValueError, OSError):
        raise
    except Exception as exc:
        raise ResourceInspectionError(
            f"Failed to inspect {path.name} before parse: {exc}"
        ) from exc
def estimate_batch_disk_requirements(
    file_paths: list[Path],
    output_folder: Path,
    temp_folder: Path | None = None,
    estimated_jpg_size_bytes: int = 1_500_000,
) -> dict[str, Any]:
    """
    Estimate worst-case temporary and final disk storage separately (Finding 7).
    - Final storage: Estimated output JPGs + JSON/CSV summary reports.
    - Temp storage: Extracted archive intermediates + decoded raster buffers + render scratch.
    - Safety margin: 50 MB minimum overhead.
    """
    final_bytes = len(file_paths) * estimated_jpg_size_bytes + 2_000_000  # Reports + JPGs
    temp_bytes = 0
    for p in file_paths:
        try:
            sz = p.stat().st_size
        except OSError:
            sz = 1_000_000
        ext = p.suffix.lower()
        if ext == ".zip":
            temp_bytes += sz * 3  # Decompression intermediate
        elif ext in MESH_EXTENSIONS:
            temp_bytes += sz * 4  # Mesh buffer conversion
        elif ext == ".psd":
            temp_bytes += sz * 2  # Layer composition scratch
        else:
            temp_bytes += max(sz, 500_000)

    safety_margin = 50 * 1024 * 1024  # 50 MB
    temp_bytes += safety_margin

    import shutil
    out_probe = output_folder if output_folder.exists() else output_folder.parent
    out_free = shutil.disk_usage(out_probe).free
    target_temp = temp_folder or Path(tempfile.gettempdir())
    temp_probe = target_temp if target_temp.exists() else target_temp.parent
    temp_free = shutil.disk_usage(temp_probe).free

    out_ok = out_free > final_bytes
    temp_ok = temp_free > temp_bytes

    return {
        "finalRequiredBytes": final_bytes,
        "tempRequiredBytes": temp_bytes,
        "outputFreeBytes": out_free,
        "tempFreeBytes": temp_free,
        "sufficient": out_ok and temp_ok,
        "error": None if (out_ok and temp_ok) else (
            f"Insufficient disk space: Output destination needs ~{final_bytes // (1024*1024)} MB "
            f"({out_free // (1024*1024)} MB free); Temp volume needs ~{temp_bytes // (1024*1024)} MB "
            f"({temp_free // (1024*1024)} MB free)."
        ),
    }
