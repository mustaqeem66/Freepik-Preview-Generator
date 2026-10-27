"""Orthographic z-buffer correctness independent of production painter path."""
from __future__ import annotations

import numpy as np
import pytest

from previewgen.renderers.depth_rasterizer import rasterize_depth_triangles

pytestmark = pytest.mark.core


def _triangle(depth: float) -> np.ndarray:
    return np.array([[2., 2., depth], [25., 2., depth],
                     [2., 25., depth]], dtype=np.float64)


@pytest.mark.parametrize("reverse", [False, True])
def test_front_triangle_wins_independent_of_submission_order(reverse):
    far = _triangle(-0.8)
    near = _triangle(0.8)
    triangles = np.array([near, far] if reverse else [far, near])
    colors = np.array([[225, 10, 10], [10, 40, 220]] if reverse
                      else [[10, 40, 220], [225, 10, 10]], dtype=np.uint8)
    output = rasterize_depth_triangles(triangles, colors, 32, 32)
    assert output.mode == "RGBA"
    assert output.getpixel((7, 7)) == (225, 10, 10, 255)
    assert output.getpixel((31, 31)) == (0, 0, 0, 0)


def test_triangle_winding_does_not_drop_coverage():
    triangle = _triangle(0.5)
    forwards = rasterize_depth_triangles([triangle], [[35, 180, 70]], 32, 32)
    backwards = rasterize_depth_triangles(
        [triangle[[0, 2, 1]]], [[35, 180, 70]], 32, 32
    )
    assert forwards.tobytes() == backwards.tobytes()


def test_interpolated_depth_changes_winner_within_one_projected_triangle():
    far = np.array([[2., 2., 0.0], [25., 2., 0.0], [2., 25., 0.0]])
    crossing = np.array([[2., 2., -1.0], [25., 2., 1.0], [2., 25., -1.0]])
    image = rasterize_depth_triangles(
        [far, crossing], [[20, 60, 220], [230, 30, 20]], 32, 32
    )
    assert image.getpixel((4, 4)) == (20, 60, 220, 255)
    assert image.getpixel((21, 4)) == (230, 30, 20, 255)


def test_degenerate_triangle_is_not_incorrectly_filled():
    degenerate = [[2., 2., 1.], [5., 5., 1.], [8., 8., 1.]]
    result = rasterize_depth_triangles([degenerate], [[255, 0, 0]], 16, 16)
    assert result.getbbox() is None


@pytest.mark.parametrize("triangles,colors,width,height,error", [
    ([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], [[255, 0, 0]], 513, 10, "512-pixel"),
    ([[[0, 0, float("nan")], [1, 0, 0], [0, 1, 0]]], [[255, 0, 0]], 8, 8, "non-finite"),
    ([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], [[260, 0, 0]], 8, 8, "0–255"),
    ([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], [], 8, 8, "RGB triplet"),
])
def test_invalid_untrusted_geometry_fails_closed(triangles, colors, width, height, error):
    with pytest.raises(ValueError, match=error):
        rasterize_depth_triangles(triangles, colors, width, height)


def test_work_and_face_count_budget_fail_closed():
    small = _triangle(0.0)
    with pytest.raises(ValueError, match="10,000-triangle"):
        rasterize_depth_triangles(
            np.tile(small, (10_001, 1, 1)),
            np.tile(np.array([[5, 5, 5]]), (10_001, 1)), 32, 32
        )
    huge = np.array([[0., 0., 1.], [512., 0., 1.], [0., 512., 1.]])
    with pytest.raises(ValueError, match="pixel-work budget"):
        rasterize_depth_triangles(
            np.tile(huge, (50, 1, 1)),
            np.tile(np.array([[5, 5, 5]]), (50, 1)), 512, 512
        )
