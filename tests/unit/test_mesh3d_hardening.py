"""3D renderer hardening: untrusted .blend execution and face-count budgets."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.core


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
    assert "--disable-auto-execution" in argv
    assert "-Y" not in argv
    assert argv.index("--disable-auto-execution") < argv.index(str(blend))


def test_heavy_model_is_subsampled_even_at_full_size(monkeypatch):
    from previewgen.renderers.mesh3d import render_3d_mesh

    face_count = 240_000
    rng = np.random.default_rng(7)
    vertices = rng.uniform(-1.0, 1.0, size=(face_count * 3, 3))
    faces = np.arange(face_count * 3, dtype=np.int64).reshape(-1, 3)
    normals = np.zeros((face_count, 3))

    class _Mesh:
        centroid = np.zeros(3)
        visual = None

    mesh = _Mesh()
    mesh.vertices = vertices  # type: ignore[attr-defined]
    mesh.faces = faces  # type: ignore[attr-defined]
    mesh.face_normals = normals  # type: ignore[attr-defined]

    drawn: list[object] = []
    original = ImageDraw.ImageDraw.polygon

    def record(self, xy, fill=None, *args, **kwargs):
        drawn.append(fill)
        return original(self, xy, fill, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "polygon", record)
    render_3d_mesh(mesh, target_dimension=2400)

    # Without a budget every one of the 240k triangles costs a Python call.
    assert 0 < len(drawn) <= 90_000
