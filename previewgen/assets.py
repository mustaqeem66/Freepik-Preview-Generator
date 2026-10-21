"""
PreviewGen asset classification and size probing.

Distinguishes *resolvable* assets (vectors and formats the renderers redraw at a
requested resolution) from *fixed-bitmap* assets (raster images and formats that
only expose an embedded preview bitmap). This drives the export-size rules:

  * ``vector`` / ``procedural`` - can be re-drawn at any size up to the cap.
  * ``raster`` - the native pixel count is the ceiling; only downscaling.

Probing is cheap and best-effort: header-only for raster images, declared
``width``/``height``/``viewBox`` for SVG. Unknown sizes return ``None`` so the
frontend can fall back to the live preview aspect ratio.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from previewgen import config as previewgen_config
from previewgen import limits

VECTOR = "vector"
PROCEDURAL = "procedural"
RASTER = "raster"

VECTOR_EXTENSIONS = frozenset({".svg", ".svgz", ".ai", ".eps"})

PROCEDURAL_EXTENSIONS = frozenset({
    ".ttf", ".otf", ".woff", ".woff2",
    ".dxf",
    ".obj", ".glb", ".gltf", ".stl", ".ply", ".3mf", ".dae",
    ".step", ".stp", ".iges", ".igs",
})


def classify_asset(source_path: Path | str) -> str:
    """Return ``vector``, ``procedural`` or ``raster`` for a source path."""
    ext = Path(source_path).suffix.lower()
    if ext == ".blend" or ext == ".eps":
        return RASTER
    if ext == ".ai" and Path(source_path).is_file():
        with open(source_path, "rb") as stream:
            if b"%PDF-" not in stream.read(1024):
                return RASTER
    if ext in VECTOR_EXTENSIONS:
        return VECTOR
    if ext in PROCEDURAL_EXTENSIONS:
        return PROCEDURAL
    return RASTER


def is_resizable(kind: str) -> bool:
    """True when the asset can be cleanly re-drawn larger than its native size."""
    return kind in (VECTOR, PROCEDURAL)


def max_output_dimension() -> int:
    return previewgen_config.MAX_EXPORT_DIMENSION


def default_render_dimension() -> int:
    return previewgen_config.DEFAULT_RENDER_DIMENSION
def calculate_export_dimensions(
    source_path: Path | str,
    requested_width: int = 0,
    requested_height: int = 0,
) -> dict[str, Any]:
    """
    Canonical, authoritative dimension calculation shared across frontend and backend.
    Honours:
    - Native aspect ratio
    - Upscaling policy (vector/procedural vs raster)
    - Maximum export dimension clamp
    - EXIF orientation
    """
    path = Path(source_path)
    kind = classify_asset(path)
    resizable = is_resizable(kind)
    native = probe_native_size(path, kind)

    max_dim = max_output_dimension()
    default_dim = default_render_dimension()

    native_w = native[0] if native else None
    native_h = native[1] if native else None

    aspect = (native_w / native_h) if (native_w and native_h) else 1.0

    if requested_width > 0 and requested_height > 0:
        req_longest = max(requested_width, requested_height)
    elif requested_width > 0:
        req_longest = requested_width
    elif requested_height > 0:
        req_longest = requested_height
    else:
        req_longest = max(native_w or 0, native_h or 0) or default_dim

    if not resizable and native_w and native_h:
        native_longest = max(native_w, native_h)
        longest = min(req_longest, native_longest)
        upscale_capped = req_longest > native_longest
    else:
        longest = min(req_longest, max_dim)
        upscale_capped = False

    longest = max(16, longest)

    if aspect >= 1.0:
        final_w = longest
        final_h = max(16, round(longest / aspect))
    else:
        final_h = longest
        final_w = max(16, round(longest * aspect))

    return {
        "width": final_w,
        "height": final_h,
        "longest": longest,
        "aspect": aspect,
        "kind": kind,
        "resizable": resizable,
        "nativeWidth": native_w,
        "nativeHeight": native_h,
        "maxDimension": max_dim,
        "upscaleCapped": upscale_capped,
    }




def _probe_svg_size(path: Path) -> tuple[int, int] | None:
    # Bounded read: SVG root tag width/height/viewBox lives in the initial chunk
    max_read = 64 * 1024
    with open(path, "rb") as stream:
        header = stream.read(max_read)
    if header[:2] == b"\x1f\x8b" or path.suffix.lower() == ".svgz":
        header = limits._gzip_decompress_limited(header, previewgen_config.MAX_SVG_DECOMPRESSED_BYTES)
    size = limits._declared_svg_size(header.decode("utf-8", errors="replace"))
    return (max(1, round(size[0])), max(1, round(size[1]))) if size else None

def _probe_raster_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as img:
            width, height = img.size
            if img.getexif().get(274) in (5, 6, 7, 8):
                width, height = height, width
            return int(width), int(height)
    except Exception:
        return None


def probe_native_size(source_path: Path | str, kind: str | None = None) -> tuple[int, int] | None:
    """Best-effort native pixel size for an asset, or ``None`` when unknown."""
    path = Path(source_path)
    resolved_kind = kind or classify_asset(path)
    if resolved_kind == VECTOR and path.suffix.lower() in (".svg", ".svgz"):
        return _probe_svg_size(path)
    if resolved_kind == RASTER:
        return _probe_raster_size(path)
    return None


def probe_asset(source_path: Path | str) -> dict[str, object]:
    """Describe an asset for the export-size control.

    Returns the classification, whether it may be enlarged, its native size when
    cheaply known, and the dimension cap / default used by the renderers.
    """
    path = Path(source_path)
    kind = classify_asset(path)
    limits.validate_source_before_parse(path)
    native = probe_native_size(path, kind)
    from previewgen.renderers.capabilities import capability_for

    capability = capability_for(path.suffix)
    return {
        "kind": kind,
        "previewSupport": capability.public() if capability else None,
        "resizable": is_resizable(kind),
        "nativeWidth": native[0] if native else None,
        "nativeHeight": native[1] if native else None,
        "maxDimension": max_output_dimension(),
        "defaultDimension": default_render_dimension(),
    }
