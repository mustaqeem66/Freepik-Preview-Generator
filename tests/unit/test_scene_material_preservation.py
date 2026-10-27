"""Regression: mixed PBR materials survive scene flattening."""
from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.core


def test_scene_normalizes_each_component_before_concatenation():
    trimesh = pytest.importorskip("trimesh")
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals

    from previewgen.renderers.mesh3d import _combine_scene_meshes, _safe_face_colors

    scene = trimesh.Scene()
    for name, rgba, offset in (
        ("red", [230, 40, 30, 255], -2.0),
        ("blue", [30, 60, 230, 255], 2.0),
    ):
        mesh = trimesh.creation.box()
        mesh.visual = TextureVisuals(material=PBRMaterial(baseColorFactor=rgba))
        transform = trimesh.transformations.translation_matrix([offset, 0, 0])
        scene.add_geometry(mesh, geom_name=name, transform=transform)

    combined = _combine_scene_meshes(scene, trimesh)
    colors = _safe_face_colors(combined, len(combined.faces))
    assert colors is not None
    assert len(colors) == len(combined.faces)
    assert np.any((colors[:, 0] > 180) & (colors[:, 2] < 80))
    assert np.any((colors[:, 2] > 180) & (colors[:, 0] < 80))
