"""
PreviewGen Source Loader
Dispatches an input file to the correct format renderer and returns a verified
RGBA PIL image.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from previewgen import config as previewgen_config
from previewgen import limits
from previewgen.config import PreviewConfig
from previewgen.renderers.cad import _load_cad_solid, _load_dwg, _load_dxf
from previewgen.renderers.creator import (
    _load_abr,
    _load_affinity,
    _load_clip,
    _load_indd,
    _load_kra,
    _load_procreate,
    _load_procreate_brush,
)
from previewgen.renderers.font import _load_font
from previewgen.renderers.mesh3d import _load_3d
from previewgen.renderers.proprietary import (
    _load_f3d,
    _load_max,
    _load_maya,
)
from previewgen.renderers.psd import _load_psd
from previewgen.renderers.vector import _load_ai, _load_eps, _load_svg


def load_source_image(
    source_path: Path,
    config: PreviewConfig | None = None,
    max_dimension: int | None = None,
    target_dimension: int | None = None,
) -> Image.Image:
    """Load an input file (2D images, PSD, 3D meshes, CAD files) into a verified RGBA PIL Image.

    ``target_dimension`` re-draws/re-samples the asset so its longest edge equals
    the requested pixel size (used for export). Vector and procedural formats are
    re-rendered crisply at that size; raster formats are only ever downscaled.
    ``max_dimension`` remains the fast-preview cap.
    """
    source_path = Path(source_path)
    if source_path.is_file():
        size_bytes = source_path.stat().st_size
        if size_bytes > previewgen_config.MAX_SOURCE_FILE_BYTES:
            raise ValueError(
                f"Source file exceeds maximum size limit ({size_bytes // (1024*1024)} MB > 500 MB): {source_path.name}"
            )
        # Reject oversized assets from cheap header/line checks before any
        # renderer parses them, so limits are enforced before memory is allocated.
        limits.validate_source_before_parse(source_path)
    ext = source_path.suffix.lower()
    if ext in (".svg", ".svgz"):
        return _load_svg(source_path, max_dimension=max_dimension, target_dimension=target_dimension)

    if ext == ".ai":
        return _load_ai(source_path, max_dimension=max_dimension, target_dimension=target_dimension)

    if ext == ".eps":
        return _load_eps(source_path, max_dimension=max_dimension, target_dimension=target_dimension)

    if ext == ".procreate":
        return _load_procreate(source_path)

    if ext in (".brush", ".brushset"):
        return _load_procreate_brush(source_path)

    if ext == ".clip":
        return _load_clip(source_path)

    if ext == ".kra":
        return _load_kra(source_path)

    if ext in (".afdesign", ".afphoto", ".afpub"):
        return _load_affinity(source_path)

    if ext == ".indd":
        return _load_indd(source_path)

    if ext == ".abr":
        return _load_abr(source_path)

    if ext in (".ttf", ".otf", ".woff", ".woff2"):
        return _load_font(source_path, target_dimension=target_dimension or max_dimension or 2400)

    if ext == ".psd":
        return _load_psd(source_path)

    if ext == ".dxf":
        return _load_dxf(source_path, target_dimension=target_dimension or max_dimension or 2400)

    if ext == ".dwg":
        return _load_dwg(source_path)

    if ext == ".max":
        return _load_max(source_path)

    if ext == ".f3d":
        return _load_f3d(source_path)

    if ext in (".mb", ".ma"):
        return _load_maya(source_path)

    if ext in (".step", ".stp", ".iges", ".igs"):
        return _load_cad_solid(
            source_path,
            config or PreviewConfig(),
            target_dimension=target_dimension or max_dimension or 2400,
        )

    if ext in previewgen_config.SUPPORTED_3D_EXTENSIONS:
        return _load_3d(
            source_path,
            config or PreviewConfig(),
            target_dimension=target_dimension or max_dimension or 2400,
        )
    # Standard raster formats (.png, .webp, .tif, .tiff)
    with Image.open(source_path) as img:
        if getattr(img, "is_animated", False):
            img.seek(0)
        img.load()
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img) or img

        if img.mode in ("I;16", "I;16L", "I;16B", "I;16N"):
            import numpy as np
            arr = (np.array(img, dtype=np.float32) / 256.0).clip(0, 255).astype(np.uint8)
            result = Image.fromarray(arr).convert("RGBA")
        elif img.mode in ("I", "F"):
            import numpy as np
            # The numeric range of a 32-bit integer or float raster depends on
            # the writer: an 8-bit scan arrives as mode "I" with 0..255 values
            # and a normalized float image tops out at 1.0. Scaling by a fixed
            # divisor rendered both almost pure black.
            arr = np.array(img, dtype=np.float64)
            peak = float(arr.max(initial=0.0))
            if peak > 255.0 or (img.mode == "F" and peak > 0.0):
                arr = arr * (255.0 / peak)
            result = Image.fromarray(arr.clip(0, 255).astype(np.uint8), mode="L").convert("RGBA")
        elif img.mode in ("CMYK", "YCbCr"):
            result = img.convert("RGB").convert("RGBA")
        else:
            result = img.convert("RGBA")

    # Raster assets are never upscaled - only ever downscaled to the target.
    if target_dimension is not None:
        rw, rh = result.size
        if max(rw, rh) > target_dimension:
            ratio = target_dimension / max(rw, rh)
            result = result.resize(
                (max(1, round(rw * ratio)), max(1, round(rh * ratio))),
                Image.Resampling.LANCZOS,
            )
    return result
