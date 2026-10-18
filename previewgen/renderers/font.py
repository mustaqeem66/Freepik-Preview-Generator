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

    # 1. Specimen Header
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.05)),
        f"{font_name}",
        fill=(15, 23, 42, 255),
        font=font_title,
    )
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.12)),
        f"TYPOGRAPHY SPECIMEN  •  {ext.upper().lstrip('.')} FORMAT",
        fill=(100, 116, 139, 255),
        font=font_pangram,
    )

    # Subtle horizontal divider
    draw.line(
        [
            (card_x + int(W * 0.05), card_y + int(H * 0.18)),
            (card_x + card_w - int(W * 0.05), card_y + int(H * 0.18)),
        ],
        fill=(226, 232, 240, 255),
        width=int(W * 0.002),
    )

    # 2. Uppercase alphabet
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.22)),
        "A B C D E F G H I J K L M",
        fill=(30, 41, 59, 255),
        font=font_alphabet,
    )
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.32)),
        "N O P Q R S T U V W X Y Z",
        fill=(30, 41, 59, 255),
        font=font_alphabet,
    )

    # 3. Lowercase alphabet
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.44)),
        "a b c d e f g h i j k l m",
        fill=(51, 65, 85, 255),
        font=font_alphabet,
    )
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.54)),
        "n o p q r s t u v w x y z",
        fill=(51, 65, 85, 255),
        font=font_alphabet,
    )

    # 4. Numerals & Punctuation
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.66)),
        "0 1 2 3 4 5 6 7 8 9 & ? ! @ # $ % *",
        fill=(71, 85, 105, 255),
        font=font_alphabet,
    )

    # Subtle horizontal divider
    draw.line(
        [
            (card_x + int(W * 0.05), card_y + int(H * 0.77)),
            (card_x + card_w - int(W * 0.05), card_y + int(H * 0.77)),
        ],
        fill=(226, 232, 240, 255),
        width=int(W * 0.002),
    )

    # 5. Classic Pangram
    draw.text(
        (card_x + int(W * 0.05), card_y + int(H * 0.82)),
        "The quick brown fox jumps over the lazy dog.",
        fill=(15, 23, 42, 255),
        font=font_pangram,
    )

    return img
