"""Opt-in bounded contact sheet for animated GIF and WebP sources.

This module deliberately reads at most nine decoded frames and does not use any
external files, filesystem paths or non-Pillow plugins.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw


MAX_CONTACT_SHEET_FRAMES = 9
MAX_CONTACT_SHEET_SOURCE_PIXELS = 16_000_000


def animated_contact_sheet(image: Image.Image) -> Image.Image:
    """Arrange at most 9 decoded frames without changing source canvas size.

    The caller must keep the Pillow source open. This is only invoked for an
    explicitly-enabled contact sheet and never changes single-frame defaults.
    Source decode work and temporary sheet dimensions are bounded.
    """
    width, height = image.size
    if width < 1 or height < 1 or width * height > MAX_CONTACT_SHEET_SOURCE_PIXELS:
        raise ValueError("Animated contact sheet exceeds the 16 MP source canvas limit")
    frame_count = min(MAX_CONTACT_SHEET_FRAMES, max(1, int(getattr(image, "n_frames", 1))))
    if frame_count == 1:
        image.seek(0)
        return image.convert("RGBA")
    columns = min(3, math.ceil(math.sqrt(frame_count)))
    rows = math.ceil(frame_count / columns)
    sheet = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    border = ImageDraw.Draw(sheet)
    for index in range(frame_count):
        # Pillow decodes/disposes each frame when seeking. Never use
        # ImageSequence.Iterator without a cap on untrusted frame counts.
        image.seek(index)
        frame = image.convert("RGBA")
        col = index % columns
        row = index // columns
        x0 = col * width // columns
        y0 = row * height // rows
        x1 = (col + 1) * width // columns
        y1 = (row + 1) * height // rows
        tile_width = max(1, x1 - x0)
        tile_height = max(1, y1 - y0)
        pad = max(1, min(tile_width, tile_height) // 30)
        frame.thumbnail(
            (max(1, tile_width - pad * 2), max(1, tile_height - pad * 2)),
            Image.Resampling.LANCZOS,
        )
        x = x0 + (tile_width - frame.width) // 2
        y = y0 + (tile_height - frame.height) // 2
        sheet.alpha_composite(frame, (x, y))
        if tile_width > 3 and tile_height > 3:
            border.rectangle(
                (x0, y0, x1 - 1, y1 - 1),
                outline=(130, 145, 160, 190), width=1,
            )
    return sheet
