"""Isolated UV+depth raster regression without pretending production PBR support."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from previewgen.renderers.depth_rasterizer import rasterize_depth_triangles

pytestmark = pytest.mark.core


def _texture() -> Image.Image:
    img = Image.new("RGB", (4, 4))
    for y in range(4):
        for x in range(4):
            if x < 2 and y < 2:
                color = (240, 30, 30)       # top left red
            elif x >= 2 and y < 2:
                color = (30, 220, 30)       # top right green
            elif x < 2:
                color = (30, 30, 230)       # bottom left blue
            else:
                color = (220, 200, 30)      # bottom right yellow
            img.putpixel((x, y), color)
    return img


def _geometry():
    vertices = np.array([[[2., 2., 0.5], [30., 2., 0.5], [2., 30., 0.5]]])
    uvs = np.array([[[0.01, 0.99], [0.99, 0.99], [0.01, 0.01]]])
    return vertices, uvs


def test_uv_coordinates_sample_distinct_texture_regions():
    tri, uv = _geometry()
    result = rasterize_depth_triangles(
        tri, [[255, 255, 255]], 32, 32, vertex_uv=uv, texture=_texture()
    )
    assert result.getpixel((5, 5)) == (240, 30, 30, 255)
    assert result.getpixel((20, 5)) == (30, 220, 30, 255)
    assert result.getpixel((5, 20)) == (30, 30, 230, 255)
    assert result.getpixel((31, 31)) == (0, 0, 0, 0)


def test_uv_texture_rgb_is_tinted_by_per_face_color():
    tri, uv = _geometry()
    result = rasterize_depth_triangles(
        tri, [[255, 0, 0]], 32, 32, vertex_uv=uv, texture=_texture()
    )
    assert result.getpixel((20, 5)) == (30, 0, 0, 255)


def test_optional_uv_does_not_modify_untextured_baseline():
    tri, uv = _geometry()
    plain = rasterize_depth_triangles(tri, [[80, 100, 120]], 32, 32)
    assert plain.getpixel((5, 5)) == (80, 100, 120, 255)


def test_winding_reversal_preserves_uv_mapping():
    tri, uv = _geometry()
    a = rasterize_depth_triangles(
        tri, [[255, 255, 255]], 32, 32, vertex_uv=uv, texture=_texture()
    )
    b = rasterize_depth_triangles(
        tri[:, [0, 2, 1], :], [[255, 255, 255]], 32, 32,
        vertex_uv=uv[:, [0, 2, 1], :], texture=_texture(),
    )
    assert a.tobytes() == b.tobytes()


def test_missing_mismatched_and_nonfinite_uv_rejected():
    tri, uv = _geometry()
    with pytest.raises(ValueError, match="both texture"):
        rasterize_depth_triangles(
            tri, [[255, 255, 255]], 32, 32, vertex_uv=uv
        )
    with pytest.raises(ValueError, match="both texture"):
        rasterize_depth_triangles(
            tri, [[255, 255, 255]], 32, 32, texture=_texture()
        )
    with pytest.raises(ValueError, match="UV shape"):
        rasterize_depth_triangles(
            tri, [[255, 255, 255]], 32, 32,
            vertex_uv=[[[0, 0], [1, 1]]], texture=_texture()
        )
    corrupt = uv.copy()
    corrupt[0, 1, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        rasterize_depth_triangles(
            tri, [[255, 255, 255]], 32, 32,
            vertex_uv=corrupt, texture=_texture()
        )


def test_oversized_or_transparent_texture_rejected():
    tri, uv = _geometry()
    huge = Image.new("RGB", (2049, 1), "red")
    with pytest.raises(ValueError, match="2048-pixel"):
        rasterize_depth_triangles(
            tri, [[255, 255, 255]], 32, 32, vertex_uv=uv, texture=huge
        )
    transparent = Image.new("RGBA", (4, 4), (200, 10, 20, 120))
    with pytest.raises(ValueError, match="transparent textures"):
        rasterize_depth_triangles(
            tri, [[255, 255, 255]], 32, 32, vertex_uv=uv, texture=transparent
        )
