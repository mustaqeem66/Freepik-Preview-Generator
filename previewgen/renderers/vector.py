"""
PreviewGen SVG Renderer
Rasterizes SVG/SVGZ vector files using resvg.
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from previewgen import config as previewgen_config
from previewgen import limits


def _load_svg(source_path: Path, max_dimension: int | None = None, target_dimension: int | None = None) -> Image.Image:
    """Rasterize an SVG/SVGZ vector file to an exact-resolution RGBA PIL image using resvg.
    Handles uncompressed .svg and gzip-compressed .svgz cleanly.
    Preserves exact declared width/height or viewBox dimensions for export.

    ``target_dimension`` re-draws the vector so its longest edge equals the
    requested pixel size (up or down) - vector artwork stays crisp at any size.
    ``max_dimension`` only ever downscales, which is what the fast UI preview uses.
    """
    try:
        import resvg_py
        raw_bytes = source_path.read_bytes()
        if raw_bytes.startswith(b"\x1f\x8b") or source_path.suffix.lower() == ".svgz":
            raw_bytes = limits._gzip_decompress_limited(raw_bytes, previewgen_config.MAX_SVG_DECOMPRESSED_BYTES)
        svg_str = raw_bytes.decode("utf-8", errors="replace")
        size = limits._declared_svg_size(svg_str)
        desired = target_dimension if target_dimension is not None else max_dimension
        width: int | None = None
        height: int | None = None
        if size and desired is not None and (target_dimension is not None or max(size) > desired):
            # Rasterize at the requested resolution, not at native size followed by
            # a bitmap upscale that permanently blurs vector edges.
            if size[0] >= size[1]:
                width = int(desired)
            else:
                height = int(desired)
        png_bytes = resvg_py.svg_to_bytes(svg_string=svg_str, width=width, height=height)
        return limits.bounded_image_from_bytes(png_bytes, "SVG render")
    except Exception as exc:
        raise RuntimeError(f"Could not render SVG file '{source_path.name}': {exc}") from exc
def _load_ai(
    source_path: Path,
    max_dimension: int | None = None,
    target_dimension: int | None = None,
) -> Image.Image:
    """Render an Adobe Illustrator (.ai) vector document.
    Supports modern dual-stream PDF AI files via pypdfium2, with fallback to embedded XMP thumbnails.
    """
    try:
        target_dim = target_dimension or max_dimension or 2400
        # 1. Try native PDFium vector rasterization (for modern PDF-compatible .ai files)
        try:
            import pypdfium2 as pdfium  # pyrefly: ignore[missing-import]  # optional .ai dependency
            with pdfium.PdfDocument(source_path) as doc:
                if len(doc) > 0:
                    # PdfPage and PdfBitmap are not context managers in pypdfium2;
                    # using `with` here raised TypeError every time, so every .ai
                    # export silently fell through to the tiny XMP thumbnail.
                    page = doc[0]
                    try:
                        w_pts, h_pts = page.get_size()
                        scale = target_dim / max(w_pts, h_pts)
                        bitmap = page.render(scale=scale, fill_color=(0, 0, 0, 0))
                        return bitmap.to_pil().convert("RGBA")
                    finally:
                        page.close()
        except Exception as exc:
            logging.debug("PDF-compatible .ai rasterization failed for %s: %s", source_path.name, exc)

        # 2. Fallback: extract embedded XMP thumbnail
        raw_bytes = source_path.read_bytes()
        import base64
        import re
        match = re.search(rb"<xmpGImg:image>([^<]+)</xmpGImg:image>", raw_bytes)
        if match:
            clean_b64 = re.sub(rb"\s+", b"", match.group(1))
            jpeg_bytes = base64.b64decode(clean_b64)
            with Image.open(BytesIO(jpeg_bytes)) as img:
                img.load()
                return img.convert("RGBA")

        # 3. Fallback: check for embedded JPEG stream inside file
        jpg_start = raw_bytes.find(b"\xff\xd8\xff")
        if jpg_start != -1:
            jpg_end = raw_bytes.find(b"\xff\xd9", jpg_start)
            if jpg_end != -1:
                try:
                    with Image.open(BytesIO(raw_bytes[jpg_start : jpg_end + 2])) as img:
                        img.load()
                        return img.convert("RGBA")
                except Exception:
                    pass

        raise ValueError(
            "This .ai file has no embedded PDF stream or thumbnail. "
            "Ensure it was saved with 'Create PDF Compatible File' enabled."
        )
    except Exception as exc:
        raise RuntimeError(f"Could not render Adobe Illustrator file '{source_path.name}': {exc}") from exc


def _load_eps(
    source_path: Path,
    max_dimension: int | None = None,
    target_dimension: int | None = None,
) -> Image.Image:
    """Render an Encapsulated PostScript (.eps) vector document.
    Supports DOS EPS binary headers with embedded TIFF previews, XMP packets, and Pillow EPS rendering.
    """
    def _finish(img: Image.Image) -> Image.Image:
        desired = target_dimension or max_dimension
        if desired is None:
            return img
        w, h = img.size
        if max(w, h) <= 0:
            return img
        if max(w, h) > desired:
            ratio = desired / max(w, h)
            return img.resize((max(1, round(w * ratio)), max(1, round(h * ratio))), Image.Resampling.LANCZOS)
        return img

    try:
        raw_bytes = source_path.read_bytes()

        # 1. Fast Path: DOS EPS binary header (0xC6D3D0C5) with embedded TIFF thumbnail
        if len(raw_bytes) >= 30:
            import struct
            magic = struct.unpack_from("<L", raw_bytes, 0)[0]
            if magic == 0xC6D3D0C5:
                t_off, t_len = struct.unpack_from("<LL", raw_bytes, 20)
                if t_off > 0 and t_len > 0 and t_off + t_len <= len(raw_bytes):
                    with Image.open(BytesIO(raw_bytes[t_off : t_off + t_len])) as img:
                        img.load()
                        return _finish(img.convert("RGBA"))

        # 2. XMP metadata thumbnail extraction (<xmpGImg:image>)
        import base64
        import re
        match = re.search(rb"<xmpGImg:image>([^<]+)</xmpGImg:image>", raw_bytes)
        if match:
            clean_b64 = re.sub(rb"\s+", b"", match.group(1))
            jpeg_bytes = base64.b64decode(clean_b64)
            with Image.open(BytesIO(jpeg_bytes)) as img:
                img.load()
                return _finish(img.convert("RGBA"))

        # 3. Standard Pillow EPS parser fallback
        try:
            with Image.open(BytesIO(raw_bytes)) as img:
                img.load()
                return _finish(img.convert("RGBA"))
        except Exception:
            pass

        raise ValueError("No embedded TIFF preview, XMP thumbnail, or readable PostScript bounding box found")
    except Exception as exc:
        raise RuntimeError(f"Could not render EPS file '{source_path.name}': {exc}") from exc
