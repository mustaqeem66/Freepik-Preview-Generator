"""
PreviewGen Typography Font Specimen Generator
Renders high-resolution specimen preview cards for TrueType (.ttf), OpenType (.otf),
and Web Fonts (.woff, .woff2) showing uppercase, lowercase, numerals, punctuation,
and a classic pangram display.
"""
from __future__ import annotations

import io
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont


def load_typeface(source_path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Load the selected face, including decoded WOFF containers; never substitute."""
    if source_path.suffix.lower() not in (".woff", ".woff2"):
        return ImageFont.truetype(str(source_path), size=size)
    with TTFont(source_path) as font:
        font.flavor = None
        buffer = io.BytesIO()
        font.save(buffer)
    return ImageFont.truetype(io.BytesIO(buffer.getvalue()), size=size)


def _fit_line(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    available_width: int,
) -> tuple[str, ImageFont.FreeTypeFont]:
    """Use the selected typeface while ensuring glyphs fit the specimen column.

    Prefer font-size reduction to ellipsizing. Very long filenames are
    truncated only when even a legible minimum size will not fit. Never
    substitute a different typeface for missing or wide glyphs.
    """
    available_width = max(1, available_width)
    initial_size = max(1, int(font.size))
    min_size = min(initial_size, max(1, round(initial_size * 0.38)))

    def fits(value: str, candidate: ImageFont.FreeTypeFont) -> bool:
        # Include the glyph's right bearing rather than trusting advance
        # width; textbbox is the actual painting bound on this renderer.
        return draw.textbbox((0, 0), value, font=candidate)[2] <= available_width

    if fits(text, font):
        return text, font

    low, high = min_size, initial_size
    best = font.font_variant(size=min_size)
    while low <= high:
        middle = (low + high) // 2
        candidate = font.font_variant(size=middle)
        if fits(text, candidate):
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    if fits(text, best):
        return text, best

    # Extremely long labels will still exceed a card at minimum readable
    # size. Keep a bounded prefix and show a visible clipping indicator.
    suffix = "..."
    if not fits(suffix, best):
        return "", best
    low, high = 0, len(text)
    accepted = 0
    while low <= high:
        middle = (low + high) // 2
        candidate = text[:middle] + suffix
        if fits(candidate, best):
            accepted = middle
            low = middle + 1
        else:
            high = middle - 1
    return text[:accepted] + suffix, best


def _load_font(source_path: Path, target_dimension: int = 2400) -> Image.Image:
    """Render a high-resolution typography specimen card for font files."""
    W, H = target_dimension, target_dimension
    ext = source_path.suffix.lower()


    # Canvas container
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Card dimensions
    margin = int(W * 0.05)
    card_w = W - 2 * margin
    card_h = H - 2 * margin
    card_x = margin
    card_y = margin

    # Draw rounded card background with subtle border
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=int(W * 0.02),
        fill=(255, 255, 255, 245),
        outline=(203, 213, 225, 255),
        width=int(W * 0.003),
    )

    # Resolve fonts at responsive sizes
    try:
        font_title = load_typeface(source_path, max(1, int(W * 0.05)))
        font_alphabet = font_title.font_variant(size=max(1, int(W * 0.048)))
        font_pangram = font_title.font_variant(size=max(1, int(W * 0.04)))
    except Exception as exc:
        raise ValueError(f"Could not load the selected font '{source_path.name}'") from exc

    font_name = source_path.stem.replace("-", " ").replace("_", " ").title()
    inner_margin = round(W * 0.10)
    left = inner_margin
    right = W - inner_margin

    def specimen_text(y: int, value: str, font: ImageFont.FreeTypeFont,
                      color: tuple[int, int, int, int]) -> None:
        label, fitted = _fit_line(draw, value, font, right - left)
        if label:
            draw.text((left, y), label, fill=color, font=fitted)

    # 1. Specimen Header
    specimen_text(card_y + int(H * 0.05), font_name, font_title, (15, 23, 42, 255))
    specimen_text(card_y + int(H * 0.12),
                  f"TYPOGRAPHY SPECIMEN  •  {ext.upper().lstrip('.')} FORMAT",
                  font_pangram, (100, 116, 139, 255))

    # Subtle horizontal divider
    draw.line(
        [
            (left, card_y + int(H * 0.18)),
            (right, card_y + int(H * 0.18)),
        ],
        fill=(226, 232, 240, 255),
        width=int(W * 0.002),
    )

    # 2. Uppercase alphabet
    specimen_text(card_y + int(H * 0.22), "A B C D E F G H I J K L M",
                  font_alphabet, (30, 41, 59, 255))
    specimen_text(card_y + int(H * 0.32), "N O P Q R S T U V W X Y Z",
                  font_alphabet, (30, 41, 59, 255))

    # 3. Lowercase alphabet
    specimen_text(card_y + int(H * 0.44), "a b c d e f g h i j k l m",
                  font_alphabet, (51, 65, 85, 255))
    specimen_text(card_y + int(H * 0.54), "n o p q r s t u v w x y z",
                  font_alphabet, (51, 65, 85, 255))

    # 4. Numerals & Punctuation
    specimen_text(card_y + int(H * 0.66),
                  "0 1 2 3 4 5 6 7 8 9 & ? ! @ # $ % *",
                  font_alphabet, (71, 85, 105, 255))

    # Subtle horizontal divider
    draw.line(
        [
            (left, card_y + int(H * 0.77)),
            (right, card_y + int(H * 0.77)),
        ],
        fill=(226, 232, 240, 255),
        width=int(W * 0.002),
    )

    # 5. Classic Pangram
    specimen_text(card_y + int(H * 0.82),
                  "The quick brown fox jumps over the lazy dog.",
                  font_pangram, (15, 23, 42, 255))

    return img
