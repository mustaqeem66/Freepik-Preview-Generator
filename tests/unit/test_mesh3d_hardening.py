"""3D renderer hardening: untrusted .blend execution and face-count budgets."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.core


def _uv_sphere(nu: int = 256, nv: int = 128):
    """A dense triangle sphere without requiring trimesh at import time."""
    u = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    v = np.linspace(0, np.pi, nv)
    verts = np.empty((nv * nu, 3))
    for j, vv in enumerate(v):
        verts[j * nu:(j + 1) * nu, 0] = np.sin(vv) * np.cos(u)
        verts[j * nu:(j + 1) * nu, 1] = np.cos(vv)
        verts[j * nu:(j + 1) * nu, 2] = np.sin(vv) * np.sin(u)
    idx = np.arange(nv * nu).reshape(nv, nu)
    a, b = idx[:-1], idx[1:]
    an, bn = np.roll(a, -1, axis=1), np.roll(b, -1, axis=1)
    faces = np.concatenate([
        np.stack([a, an, b], axis=-1).reshape(-1, 3),
        np.stack([an, bn, b], axis=-1).reshape(-1, 3),
    ])
    return SimpleNamespace(
        vertices=verts,
        faces=faces,
        face_normals=np.zeros((len(faces), 3)),
        visual=None,
    )


def _box_mesh(extents=(1.0, 1.0, 4.0)):
    x, y, z = (edge / 2.0 for edge in extents)
    vertices = np.array([
        (-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z),
        (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z),
    ])
    faces = np.array([
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ])
    tri = vertices[faces]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return SimpleNamespace(vertices=vertices, faces=faces, face_normals=normals, visual=None)


def test_blend_render_disables_script_auto_execution(monkeypatch, tmp_path):
    """A .blend is untrusted input; Blender must not run scripts inside it."""
    from previewgen.renderers import mesh3d

    calls: list[list[str]] = []

    def fake_run(argv, timeout):
        calls.append(list(argv))

    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"not really a blend file")

    monkeypatch.setattr(mesh3d.proc, "run_with_tree_timeout", fake_run)
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/blender")
    # No embedded thumbnail: force the Blender fallback path.
    monkeypatch.setattr(mesh3d, "extract_blend_thumbnail", lambda _path: None)

    # The fake process never writes out.png, so the renderer ends in its
    # "cannot preview" error; we only care about the command it built.
    with pytest.raises(RuntimeError):
        mesh3d._load_3d(blend, mesh3d.PreviewConfig())

    assert len(calls) == 1
    argv = calls[0]
    assert argv[1] == "-b"
    assert "--disable-autoexec" in argv
    assert "--disable-auto-execution" not in argv
    assert argv.index("--disable-autoexec") < argv.index(str(blend))


def test_dense_mesh_draws_every_face_without_holes(monkeypatch):
    """Face striding used to remove every other triangle at preview sizes,
    leaving a mesh full of one-pixel holes. Every face must be drawn."""
    from previewgen.renderers.mesh3d import render_3d_mesh

    mesh = _uv_sphere()  # 65,024 faces

    drawn: list[object] = []
    original = ImageDraw.ImageDraw.polygon

    def record(self, xy, fill=None, *args, **kwargs):
        drawn.append(fill)
        return original(self, xy, fill, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "polygon", record)
    image = render_3d_mesh(mesh, target_dimension=400)

    assert len(drawn) == len(mesh.faces)
    alpha = np.asarray(image)[:, :, 3]
    yy, xx = np.ogrid[:400, :400]
    interior = ((yy - 200) ** 2 + (xx - 200) ** 2) < 120 ** 2
    assert (alpha[interior] > 0).all(), "dense mesh left holes in its interior"


def test_untextured_pbr_glb_renders(tmp_path):
    """An untextured PBR material yields a single RGBA in trimesh; it must not
    crash the renderer (previously IndexError inside face_colors)."""
    trimesh = pytest.importorskip("trimesh")
    from trimesh.visual.material import PBRMaterial
    from trimesh.visual.texture import TextureVisuals

    from previewgen.config import PreviewConfig
    from previewgen.renderers.mesh3d import _load_3d

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.visual = TextureVisuals(
        material=PBRMaterial(baseColorFactor=[220, 90, 40, 255])
    )
    path = tmp_path / "pbr.glb"
    path.write_bytes(mesh.export(file_type="glb"))

    image = _load_3d(path, PreviewConfig(), target_dimension=128)
    pixels = np.asarray(image)[:, :, :]
    opaque = pixels[pixels[:, :, 3] > 0][:, :3]
    assert len(opaque) > 0
    # The material's base color survived the visual conversion.
    assert (opaque[:, 0] > opaque[:, 1]).mean() > 0.8


def test_z_up_models_are_rotated_upright():
    from previewgen.renderers.mesh3d import render_3d_mesh

    mesh = _box_mesh(extents=(1.0, 1.0, 4.0))

    def span(image):
        alpha = np.asarray(image)[:, :, 3]
        ys, xs = np.nonzero(alpha)
        return xs.max() - xs.min() + 1, ys.max() - ys.min() + 1

    width, height = span(render_3d_mesh(mesh, yaw_deg=0, pitch_deg=0, z_up=True))
    assert height > 2 * width

    flat_width, flat_height = span(
        render_3d_mesh(mesh, yaw_deg=0, pitch_deg=0, z_up=False)
    )
    assert flat_height <= 1.5 * flat_width


def test_non_finite_vertices_are_rejected():
    from previewgen.renderers.mesh3d import render_3d_mesh

    mesh = _box_mesh()
    mesh.vertices[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        render_3d_mesh(mesh, target_dimension=64)


def test_empty_mesh_is_rejected():
    from previewgen.renderers.mesh3d import render_3d_mesh

    mesh = SimpleNamespace(
        vertices=np.zeros((0, 3)), faces=np.zeros((0, 3), dtype=np.int64), visual=None
    )
    with pytest.raises(ValueError, match="no vertices"):
        render_3d_mesh(mesh, target_dimension=64)


def test_backfacing_mesh_renders_two_sided():
    from previewgen.renderers.mesh3d import render_3d_mesh

    mesh = _box_mesh()
    mesh.face_normals = np.tile([0.0, 0.0, -1.0], (len(mesh.faces), 1))
    image = render_3d_mesh(mesh, target_dimension=64)
    assert np.asarray(image)[:, :, 3].any()
