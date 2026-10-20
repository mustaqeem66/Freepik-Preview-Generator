"""
PreviewGen Composite Renderer
Builds the diagonal checkerboard/solid background and overlays branding/logo
and watermark text onto a loaded source image.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from previewgen.config import (
    CHECKER_DARK,
    CHECKER_LIGHT,
    DEFAULT_TEXT,
    SOLID_COLOR,
    PreviewConfig,
)


def _font(size: int, font_path: str = "") -> Any:
    if font_path and Path(font_path).is_file():
        from previewgen.renderers.font import load_typeface
        return load_typeface(Path(font_path), size)
    candidates: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR") or os.environ.get("SYSTEMROOT") or "C:/Windows")
        fonts_dir = windir / "Fonts"
        for name in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "arial.ttf"):
            candidates.append(fonts_dir / name)
    elif sys.platform == "darwin":
        for p in (
            "/System/Library/Fonts/SFProDisplay-Bold.otf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial Bold.ttf",
        ):
            candidates.append(Path(p))
    else:
        for p in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ):
            candidates.append(Path(p))

    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _checker_tile(size: int) -> Image.Image:
    tile = Image.new("RGBA", (size * 2, size * 2), CHECKER_LIGHT)
    draw = ImageDraw.Draw(tile)
    draw.rectangle((size, 0, size * 2 - 1, size - 1), fill=CHECKER_DARK)
    draw.rectangle((0, size, size - 1, size * 2 - 1), fill=CHECKER_DARK)
    return tile


def make_background(
    width: int,
    height: int,
    invert_triangles: bool = True,
    solid_color: tuple[int, int, int] = SOLID_COLOR,
) -> Image.Image:
    """Create two equal-area triangles divided from bottom-left to top-right.

    invert_triangles=True:  Left is solid color, Right is checkerboard (transparent).
    invert_triangles=False: Left is checkerboard, Right is solid color.
    """
    if width < 1 or height < 1:
        raise ValueError("Invalid image dimensions")

    checker_size = max(8, min(96, round(min(width, height) / 64)))
    tile = _checker_tile(checker_size)
    checker = Image.new("RGBA", (width, height), CHECKER_LIGHT)
    for y in range(0, height, tile.height):
        for x in range(0, width, tile.width):
            checker.paste(tile, (x, y))

    solid = Image.new("RGBA", (width, height), (*solid_color, 255))

    # Triangle mask for the upper-left half
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon(
        [(0, 0), (width - 1, 0), (0, height - 1)], fill=255
    )

    if invert_triangles:
        # Left half is solid color, right half is checkerboard
        background = checker.copy()
        background.paste(solid, (0, 0), mask)
    else:
        # Left half is checkerboard, right half is solid color
        background = solid.copy()
        background.paste(checker, (0, 0), mask)

    # Draw subtle separator line along diagonal with contrasting tone
    draw = ImageDraw.Draw(background)
    lum = solid_color[0] * 0.299 + solid_color[1] * 0.587 + solid_color[2] * 0.114
    sep_rgb = (225, 228, 232, 255) if lum > 120 else (80, 90, 105, 255)
    draw.line(
        [(0, height - 1), (width - 1, 0)],
        fill=sep_rgb,
        width=max(1, round(min(width, height) / 1000)),
    )
    return background


def _calculate_text_position(
    image_size: tuple[int, int],
    text_size: tuple[int, int],
    position: str = "top-left",
    object_bounds: tuple[int, int, int, int] | None = None,
) -> tuple[int, int]:
    width, height = image_size
    tw, th = text_size

    # Responsive padding proportional to resolution
    pad_x = max(24, min(140, round(width * 0.038)))
    pad_y = max(24, min(140, round(height * 0.038)))

    pos = position.lower().strip()
    if pos == "top-left":
        x = pad_x
        y = pad_y
    elif pos == "top-right":
        x = width - tw - pad_x
        y = pad_y
    elif pos == "bottom-left":
        x = pad_x
        y = height - th - pad_y
    elif pos == "bottom-right":
        x = width - tw - pad_x
        y = height - th - pad_y
    elif pos == "center":
        if object_bounds:
            left, top, right, bottom = object_bounds
            cx = (left + right) // 2
            cy = (top + bottom) // 2
        else:
            cx = width // 2
            cy = height // 2
        x = cx - tw // 2
        y = cy - th // 2
    else:
        x = pad_x
        y = pad_y

    x = max(10, min(width - tw - 10, x))
    y = max(10, min(height - th - 10, y))
    return x, y


def compose_preview(
    source: Image.Image,
    config: PreviewConfig | None = None,
    text: str | None = None,
    position: str = "top-left",
    opacity: float = 0.9,
    invert_triangles: bool = True,
) -> Image.Image:
    """Composite preview without crop, trim, resize, rotation, or distortion."""
    if config is None:
        actual_text = text if text is not None else DEFAULT_TEXT
        config = PreviewConfig(
            text=actual_text,
            position=position,
            opacity=opacity,
            invert_triangles=invert_triangles,
        )

    original = source.convert("RGBA")
    width, height = original.size
    alpha_min, alpha_max = original.getchannel("A").getextrema()
    if alpha_max == 0:
        raise ValueError("Image is completely transparent (empty canvas)")

    bg = make_background(
        width,
        height,
        invert_triangles=config.invert_triangles,
        solid_color=config.solid_color,
    )
    result = Image.alpha_composite(bg, original)

    # ── 1. Custom Logo / Icon Branding Overlay ──
    if config.logo_path and Path(config.logo_path).is_file():
        try:
            # Lazy import avoids a circular dependency with the loader.
            from previewgen.renderers.loader import load_source_image

            logo_file = Path(config.logo_path)
            logo_img = load_source_image(logo_file)
            base_dim = round(min(width, height) * 0.16 * max(0.2, min(3.0, config.logo_scale)))
            lw, lh = logo_img.size
            if max(lw, lh) > 0:
                ratio = base_dim / max(lw, lh)
                target_lw = max(16, round(lw * ratio))
                target_lh = max(16, round(lh * ratio))
                logo_scaled = logo_img.resize((target_lw, target_lh), Image.Resampling.LANCZOS)

                clamped_logo_op = max(0.0, min(1.0, config.logo_opacity))
                if clamped_logo_op < 0.99:
                    lr, lg, lb, la = logo_scaled.split()
                    la = la.point(lambda p: round(p * clamped_logo_op))
                    logo_scaled.putalpha(la)

                lx = max(
                    0, min(width - target_lw, round((width - target_lw) * max(0.0, min(1.0, config.logo_pos_x))))
                )
                ly = max(
                    0, min(height - target_lh, round((height - target_lh) * max(0.0, min(1.0, config.logo_pos_y))))
                )

                logo_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
                logo_layer.paste(logo_scaled, (lx, ly))
                result = Image.alpha_composite(result, logo_layer)
        except Exception:
            pass

    # ── 2. Watermark Text Overlay ──
    label = config.text.strip()
    if label:
        base_font_size = round(min(width, height) * 0.038 * config.font_scale)
        font_size = max(14, min(240, base_font_size))
        font = _font(font_size, config.font_path)

        multiplier = max(0.5, config.outline_thickness / 2.0)
        stroke = max(1, round(font_size * 0.075 * multiplier)) if config.has_outline else 0

        draw_calc = ImageDraw.Draw(result)
        box = draw_calc.textbbox((0, 0), label, font=font, stroke_width=stroke)
        tw = box[2] - box[0]
        th = box[3] - box[1]

        # Freeform coordinates only apply when the caller chose "custom";
        # comparing the sliders to their default values instead let a stale
        # slider silently override an explicitly requested preset.
        if config.position == "custom":
            x = max(0, min(width - tw, round((width - tw) * max(0.0, min(1.0, config.text_pos_x)))))
            y = max(0, min(height - th, round((height - th) * max(0.0, min(1.0, config.text_pos_y)))))
        else:
            obj_bounds = original.getchannel("A").getbbox()
            x, y = _calculate_text_position(result.size, (int(tw), int(th)), config.position, obj_bounds)

        text_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(text_layer)

        clamped_opacity = max(0.0, min(1.0, config.opacity))
        alpha_fill = round(255 * clamped_opacity)
        fill_color = (*config.text_color, alpha_fill)

        draw_x = x - box[0]
        draw_y = y - box[1]

        if config.has_outline:
            stroke_fill = (*config.outline_color, alpha_fill)
            t_draw.text(
                (draw_x, draw_y),
                label,
                font=font,
                fill=fill_color,
                stroke_width=stroke,
                stroke_fill=stroke_fill,
            )
        else:
            t_draw.text(
                (draw_x, draw_y),
                label,
                font=font,
                fill=fill_color,
            )

        result = Image.alpha_composite(result, text_layer)
    return result.convert("RGB")
