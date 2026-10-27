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
MAX_DEPTH_TEXTURE_DIMENSION = 2048


def rasterize_depth_triangles(
    screen_triangles,
    face_colors,
    width: int,
    height: int,
    *,
    vertex_uv=None,
    texture: Image.Image | None = None,
) -> Image.Image:
    """Render fully opaque RGB triangles with interpolated orthographic depth.

    screen_triangles: (N, 3, 3), each vertex (x_px, y_px, z), larger z is
    nearer the camera. face_colors: (N, 3) RGB bytes. Pixel centers are tested,
    irrespective of triangle winding or triangle input order.

    All allocations/work are bounded. Invalid coordinates, oversized output or
    an excessive total covered bounding-box area fail closed, not partially.
    Optional UVs: (N, 3, 2), matching triangle vertices; use an already
    decoded, fully opaque PIL texture with nearest-neighbour repeat sampling.
    V=1 is image top, V=0 is image bottom. Face RGB tints texels.
    Normals, alpha blending, perspective correction and PBR are NOT supported.
    """
    import numpy as np

    if not isinstance(width, int) or not isinstance(height, int) or (
        width < 1 or height < 1 or width > MAX_DEPTH_DIMENSION or height > MAX_DEPTH_DIMENSION
    ):
        raise ValueError("Depth rasterizer canvas exceeds the 512-pixel per-side limit")

    # Check cheap sequence lengths before NumPy conversion allocates an array.
    # A hostile caller must not pass millions of triangles just to be rejected.
    try:
        if len(screen_triangles) > MAX_DEPTH_TRIANGLES:
            raise ValueError("Depth rasterizer exceeds the 10,000-triangle limit")
    except TypeError:
        pass

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

    if (vertex_uv is None) != (texture is None):
        raise ValueError("Depth rasterizer requires both texture and vertex UV coordinates")
    uvs = None
    texture_pixels = None
    if texture is not None:
        if not isinstance(texture, Image.Image):
            raise ValueError("Depth rasterizer texture must be a PIL image")
        tx_width, tx_height = texture.size
        if not (1 <= tx_width <= MAX_DEPTH_TEXTURE_DIMENSION and
                1 <= tx_height <= MAX_DEPTH_TEXTURE_DIMENSION):
            raise ValueError("Depth rasterizer texture exceeds the 2048-pixel per-side limit")
        uvs = np.asarray(vertex_uv, dtype=np.float64)
        if uvs.shape != (face_count, 3, 2):
            raise ValueError("Depth rasterizer vertex UV shape must be (N, 3, 2)")
        if not np.isfinite(uvs).all() or np.any(np.abs(uvs) > 10_000):
            raise ValueError("Depth rasterizer has non-finite or excessive vertex UV coordinates")
        rgba_texture = texture.convert("RGBA")
        if rgba_texture.getchannel("A").getextrema() != (255, 255):
            raise ValueError("Depth rasterizer cannot interpret transparent textures")
        texture_pixels = np.asarray(rgba_texture, dtype=np.uint8)

    output = np.zeros((height, width, 4), dtype=np.uint8)
    depth = np.full((height, width), -np.inf, dtype=np.float64)
    work = 0

    for index, (triangle, color) in enumerate(zip(triangles, colors)):
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
            if texture_pixels is None:
                target[nearest, :3] = np.asarray(color, dtype=np.uint8)
            else:
                # UVs interpolate at the SAME nearest-depth pixel positions.
                # GL repeat addressing; coordinate v is bottom-up in texture.
                uv = uvs[index]
                u = np.mod(w0 * uv[0, 0] + w1 * uv[1, 0] + w2 * uv[2, 0], 1.0)
                v = np.mod(w0 * uv[0, 1] + w1 * uv[1, 1] + w2 * uv[2, 1], 1.0)
                tex_h, tex_w = texture_pixels.shape[:2]
                tex_x = np.minimum(tex_w - 1, (u * tex_w).astype(np.int64))
                tex_y = np.minimum(tex_h - 1, ((1.0 - v) * tex_h).astype(np.int64))
                texels = texture_pixels[tex_y, tex_x, :3]
                tint = np.asarray(color, dtype=np.float64) / 255.0
                target[nearest, :3] = np.rint(
                    texels[nearest].astype(np.float64) * tint
                ).astype(np.uint8)
            target[nearest, 3] = 255

    return Image.fromarray(output, "RGBA")
