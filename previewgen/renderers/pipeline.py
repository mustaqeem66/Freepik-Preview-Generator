"""
PreviewGen Render Pipeline
High-level helpers that load a source asset, compose the branded preview, and
persist it to disk or JPEG bytes.
"""
from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from PIL import Image

from previewgen import limits
from previewgen.assets import classify_asset, is_resizable
from previewgen.config import DEFAULT_TEXT, PreviewConfig
from previewgen.renderers.compose import compose_preview
from previewgen.renderers.loader import load_source_image


def _export_target_longest(config: PreviewConfig) -> int | None:
    """Longest-edge target for an export, or ``None`` for native/default size.

    The lock-aspect UI gives both a width and a height; the larger value is the
    requested longest edge, which preserves each asset's own aspect ratio (so the
    same setting is meaningful for a whole batch).
    """
    width = int(getattr(config, "output_width", 0) or 0)
    height = int(getattr(config, "output_height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    limits.check_output_size(width, height)
    return max(width, height)


def _downscale_longest(image: Image.Image, target: int) -> Image.Image:
    """Shrink an image so its longest edge is ``target`` (never enlarges)."""
    width, height = image.size
    longest = max(width, height)
    if longest <= target:
        return image
    ratio = target / longest
    return image.resize(
        (max(1, round(width * ratio)), max(1, round(height * ratio))),
        Image.Resampling.LANCZOS,
    )


def generate_file(
    source_path: Path,
    output_path: Path,
    config: PreviewConfig | None = None,
    text: str | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    if config is None:
        config = PreviewConfig(text=text if text is not None else DEFAULT_TEXT)

    if is_cancelled and is_cancelled():
        raise RuntimeError("Cancelled before rendering image")

    kind = classify_asset(source_path)
    target = _export_target_longest(config)
    resizable = is_resizable(kind)
    # Vector / procedural assets are re-drawn crisply at the target size; raster
    # assets are loaded at native then only ever downscaled.
    source = load_source_image(
        source_path,
        config,
        target_dimension=target if (target is not None and resizable) else None,
    )

    if is_cancelled and is_cancelled():
        raise RuntimeError("Cancelled during image preparation")

    if target is not None and not resizable:
        source = _downscale_longest(source, target)

    output = compose_preview(source, config)

    if is_cancelled and is_cancelled():
        raise RuntimeError("Cancelled before saving output")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import uuid
    temp_name = f".tmp_{output_path.stem}_{uuid.uuid4().hex[:8]}.jpg"
    temp_path = output_path.parent / temp_name
    try:
        output.save(temp_path, format="JPEG", quality=96, subsampling=0, optimize=True)
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)



def preview_jpeg_bytes(
    source_path: Path | str,
    config: PreviewConfig | None = None,
    text: str | None = None,
    max_dimension: int = 850,
) -> tuple[bytes, int, int]:
    source_path = Path(source_path)
    if config is None:
        config = PreviewConfig(text=text if text is not None else DEFAULT_TEXT)

    source = load_source_image(source_path, config, max_dimension=max_dimension)
    orig_w, orig_h = source.size
    if max(orig_w, orig_h) > max_dimension:
        ratio = max_dimension / max(orig_w, orig_h)
        tw = max(1, round(orig_w * ratio))
        th = max(1, round(orig_h * ratio))
        source = source.resize((tw, th), Image.Resampling.BILINEAR)

    preview = compose_preview(source, config)

    buffer = BytesIO()
    # P1 root cause 11: fast preview JPEG encoding without expensive optimization passes
    preview.save(buffer, format="JPEG", quality=80, optimize=False)
    return buffer.getvalue(), orig_w, orig_h



def source_preview_jpeg_bytes(
    source_path: Path | str,
    max_dimension: int = 850,
) -> tuple[bytes, int, int]:
    """Preview unbranded source content, not the branded diagonal JPG layout.

    This is a *view of decoded source artwork*, not a lossless source dump.
    Transparent pixels are displayed over a neutral checkerboard, and the
    resulting bounded RGB image is encoded to JPEG for the private loopback
    preview server. Runs only in a renderer child process.
    """
    if not 1 <= max_dimension <= 850:
        raise ValueError("Source preview size must be between 1 and 850")
    source = load_source_image(
        Path(source_path), PreviewConfig(text="", opacity=0.0),
        max_dimension=max_dimension,
    ).convert("RGBA")
    original_width, original_height = source.size
    if max(source.size) > max_dimension:
        source.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    from PIL import ImageDraw

    checker = Image.new("RGBA", source.size, (242, 244, 247, 255))
    draw = ImageDraw.Draw(checker)
    tile = 16
    for y in range(0, source.height, tile):
        for x in range(0, source.width, tile):
            if (x // tile + y // tile) % 2:
                draw.rectangle(
                    (x, y, min(source.width - 1, x + tile - 1),
                     min(source.height - 1, y + tile - 1)),
                    fill=(216, 220, 227, 255),
                )
    flattened = Image.alpha_composite(checker, source).convert("RGB")
    buffer = BytesIO()
    flattened.save(buffer, format="JPEG", quality=85, optimize=False)
    return buffer.getvalue(), original_width, original_height
