"""Bounded CPU depth rasterization kernel for future 3D renderer integration.

This is an isolated correctness mechanism, not a production PBR/UV renderer.
The painter-based renderer remains the default until image oracles certify this
kernel at fixed commits on all desktop operating systems.
"""
from __future__ import annotations

import math

from PIL import Image

MAX_DEPTH_DIMENSION = 512
MAX_DEPTH_TRIANGLES = 10_000
MAX_DEPTH_WORK_PIXELS = 8_000_000


def rasterize_depth_triangles(
    screen_triangles,
    face_colors,
    width: int,
    height: int,
) -> Image.Image:
    """Render fully opaque RGB triangles with interpolated orthographic depth.

    screen_triangles: (N, 3, 3), each vertex (x_px, y_px, z), larger z is
    nearer the camera. face_colors: (N, 3) RGB bytes. Pixel centers are tested,
    irrespective of triangle winding or triangle input order.

    All allocations/work are bounded. Invalid coordinates, oversized output or
    an excessive total covered bounding-box area fail closed, not partially.
    This kernel does not yet support UV textures, normals, transparency or PBR.
    """
    import numpy as np

    if not isinstance(width, int) or not isinstance(height, int) or (
        width < 1 or height < 1 or width > MAX_DEPTH_DIMENSION or height > MAX_DEPTH_DIMENSION
    ):
        raise ValueError("Depth rasterizer canvas exceeds the 512-pixel per-side limit")

    triangles = np.asarray(screen_triangles, dtype=np.float64)
    colors = np.asarray(face_colors)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3):
        raise ValueError("Expected projected triangle array shape (N, 3, 3)")
    face_count = len(triangles)
    if face_count > MAX_DEPTH_TRIANGLES:
        raise ValueError("Depth rasterizer exceeds the 10,000-triangle limit")
    if colors.shape != (face_count, 3) or not np.issubdtype(colors.dtype, np.number):
        raise ValueError("Expected one RGB triplet per projected triangle")
    if not np.isfinite(triangles).all() or not np.isfinite(colors).all():
        raise ValueError("Depth rasterizer received non-finite geometry or colors")
    if np.any(colors < 0) or np.any(colors > 255):
        raise ValueError("Depth rasterizer RGB colors must be in the 0–255 range")

    output = np.zeros((height, width, 4), dtype=np.uint8)
    depth = np.full((height, width), -np.inf, dtype=np.float64)
    work = 0

    for triangle, color in zip(triangles, colors):
        x0, y0, z0 = triangle[0]
        x1, y1, z1 = triangle[1]
        x2, y2, z2 = triangle[2]
        denominator = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
        if abs(denominator) <= 1e-12:
            continue  # Degenerate projected triangle.

        min_x = max(0, int(math.floor(min(x0, x1, x2))))
        min_y = max(0, int(math.floor(min(y0, y1, y2))))
        max_x = min(width - 1, int(math.ceil(max(x0, x1, x2))))
        max_y = min(height - 1, int(math.ceil(max(y0, y1, y2))))
        if min_x > max_x or min_y > max_y:
            continue

        bbox_pixels = (max_x - min_x + 1) * (max_y - min_y + 1)
        work += bbox_pixels
        if work > MAX_DEPTH_WORK_PIXELS:
            raise ValueError("Depth rasterizer exceeds its bounded pixel-work budget")

        pixel_x = np.arange(min_x, max_x + 1, dtype=np.float64)[None, :] + 0.5
        pixel_y = np.arange(min_y, max_y + 1, dtype=np.float64)[:, None] + 0.5

        # Barycentric coverage with both clockwise and counterclockwise input.
        w0 = ((x1 - pixel_x) * (y2 - pixel_y) -
              (y1 - pixel_y) * (x2 - pixel_x)) / denominator
        w1 = ((x2 - pixel_x) * (y0 - pixel_y) -
              (y2 - pixel_y) * (x0 - pixel_x)) / denominator
        w2 = 1.0 - w0 - w1
        covered = (w0 >= -1e-10) & (w1 >= -1e-10) & (w2 >= -1e-10)
        if not covered.any():
            continue

        pixel_depth = w0 * z0 + w1 * z1 + w2 * z2
        existing = depth[min_y:max_y + 1, min_x:max_x + 1]
        nearest = covered & (pixel_depth > existing)
        if nearest.any():
            existing[nearest] = pixel_depth[nearest]
            target = output[min_y:max_y + 1, min_x:max_x + 1]
            target[nearest, :3] = np.asarray(color, dtype=np.uint8)
            target[nearest, 3] = 255

    return Image.fromarray(output, "RGBA")
