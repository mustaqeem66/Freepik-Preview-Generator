"""
PreviewGen 3D Mesh Renderer
Software-renders triangle meshes (.obj, .glb, .gltf, .stl, .ply, .3mf, .dae,
.blend) to transparent RGBA images from any yaw/pitch angle.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from previewgen import limits, proc
from previewgen.config import PreviewConfig
from previewgen.renderers.proprietary import extract_blend_thumbnail

_MESH_CACHE: dict[tuple[str, float], Any] = {}


def render_3d_mesh(
    mesh,
    yaw_deg: float = 45.0,
    pitch_deg: float = 30.0,
    model_color: tuple[int, int, int] = (120, 130, 160),
    target_dimension: int = 2400,
) -> Image.Image:
    """Render a 3D mesh from any yaw/pitch angle to a transparent RGBA PIL Image."""
    import numpy as np

    W, H = target_dimension, target_dimension
    if not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))

    verts = mesh.vertices - mesh.centroid
    norms = np.linalg.norm(verts, axis=1)
    max_radius = float(np.max(norms)) if len(norms) > 0 else 1.0
    if max_radius <= 0 or not np.isfinite(max_radius):
        max_radius = 1.0
    verts = verts / max_radius

    yaw = np.radians(yaw_deg)
    pitch = np.radians(pitch_deg)

    Ry = np.array([
        [np.cos(yaw), 0, np.sin(yaw)],
        [0, 1, 0],
        [-np.sin(yaw), 0, np.cos(yaw)],
    ])
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(pitch), -np.sin(pitch)],
        [0, np.sin(pitch), np.cos(pitch)],
    ])
    R = Rx @ Ry

    v_rot = verts @ R.T
    scale = min(W, H) * 0.42
    pts_2d = np.column_stack([v_rot[:, 0], -v_rot[:, 1]]) * scale + np.array([W / 2, H / 2])
    pts_2d = np.nan_to_num(pts_2d, nan=W / 2.0)

    # Point cloud fallback when no faces exist
    if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
        result_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(result_img)
        pt_col = (*model_color, 220)
        step = max(1, len(pts_2d) // 25_000)
        for pt in pts_2d[::step]:
            draw.ellipse([pt[0] - 2, pt[1] - 2, pt[0] + 2, pt[1] + 2], fill=pt_col)
        return result_img

    normals = (
        mesh.face_normals
        if hasattr(mesh, "face_normals") and mesh.face_normals is not None
        else np.zeros((len(mesh.faces), 3))
    )
    n_rot = np.nan_to_num(normals @ R.T, nan=0.0)
    # Visible face determination and depth sorting (Finding: Hardware acceleration & optimized vector raster)
    visible_mask = n_rot[:, 2] > -0.55
    vis_indices = np.where(visible_mask)[0]
    if len(vis_indices) == 0:
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))

    faces_vis = mesh.faces[vis_indices]
    face_z = v_rot[faces_vis].mean(axis=1)[:, 2]
    vis_order = vis_indices[np.argsort(face_z)]

    # Optimization: subsample faces during fast live preview for heavy models
    if target_dimension <= 1000 and len(vis_order) > 25_000:
        stride = max(2, len(vis_order) // 20_000)
        vis_order = vis_order[::stride]

    light_dir = np.array([0.45, 0.65, 0.61])
    light_dir /= np.linalg.norm(light_dir)
    diffuse = np.nan_to_num(np.abs(n_rot[vis_order] @ light_dir) * 0.72, nan=0.0)
    ambient = 0.35
    intensity = np.clip(ambient + diffuse, 0.0, 1.0)

    has_face_colors = (
        hasattr(mesh, "visual")
        and getattr(mesh.visual, "defined", False)
        and hasattr(mesh.visual, "face_colors")
        and mesh.visual.face_colors is not None
        and len(mesh.visual.face_colors) == len(mesh.faces)
    )

    default_base = np.array(model_color, dtype=float)
    base_colors = (
        mesh.visual.face_colors[vis_order, :3].astype(float)
        if has_face_colors
        else default_base
    )
    lit_colors = np.clip(intensity[:, None] * base_colors, 0, 255).astype(np.uint8)
    ordered_faces = mesh.faces[vis_order]
    ordered_pts = pts_2d[ordered_faces]  # shape: (N, 3, 2)

    result_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(result_img)

    for i in range(len(vis_order)):
        poly = ordered_pts[i]
        points = [(poly[0, 0], poly[0, 1]), (poly[1, 0], poly[1, 1]), (poly[2, 0], poly[2, 1])]
        draw.polygon(points, fill=tuple(lit_colors[i]))

    return result_img


def _load_3d(source_path: Path, config: PreviewConfig, target_dimension: int = 2400) -> Image.Image:
    """Load and render 3D formats (.obj, .gltf, .glb, .stl, .ply, .blend) into an RGBA PIL image."""
    ext = source_path.suffix.lower()

    if ext == ".blend":
        # 1. Zero-dependency extraction: read embedded scene thumbnail saved in the .blend file
        thumb = extract_blend_thumbnail(source_path)
        if thumb is not None:
            return thumb

        # 2. Fallback to local Blender binary if installed
        import shutil
        import sys
        import tempfile

        blender_bin = shutil.which("blender")
        if not blender_bin and sys.platform == "win32":
            prog_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            foundation = prog_files / "Blender Foundation"
            if foundation.is_dir():
                matches = sorted(foundation.glob("Blender */blender.exe"))
                if matches:
                    blender_bin = str(matches[-1])
        elif not blender_bin and sys.platform == "darwin":
            mac_b = Path("/Applications/Blender.app/Contents/MacOS/blender")
            if mac_b.exists():
                blender_bin = str(mac_b)

        if blender_bin:
            with tempfile.TemporaryDirectory() as tmp_dir:
                out_png = Path(tmp_dir) / "render.png"
                script_py = Path(tmp_dir) / "render_script.py"
                script_content = (
                    "import bpy\n"
                    "bpy.context.scene.render.film_transparent = True\n"
                    "bpy.context.scene.render.image_settings.file_format = 'PNG'\n"
                    "bpy.context.scene.render.image_settings.color_mode = 'RGBA'\n"
                    f"bpy.context.scene.render.filepath = {repr(str(out_png))}\n"
                    "bpy.ops.render.render(write_still=True)\n"
                )
                script_py.write_text(script_content, encoding="utf-8")
                proc.run_with_tree_timeout(
                    [blender_bin, "-b", "-Y", str(source_path), "-P", str(script_py)],
                    timeout=60,
                )
                if out_png.exists():
                    with Image.open(out_png) as img:
                        img.load()
                        return img.convert("RGBA")

        raise RuntimeError(
            "This .blend file has no embedded preview thumbnail. "
            "To preview it, either install Blender or export the model to .glb, .gltf, or .obj "
            "(which render natively with full 360° controls)!"
        )

    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError(
            "trimesh is required for 3D model preview generation. Run: pip install trimesh"
        ) from exc

    source_path = Path(source_path).resolve()
    mtime = source_path.stat().st_mtime if source_path.exists() else 0.0
    key = (str(source_path), mtime)
    if key in _MESH_CACHE:
        mesh = _MESH_CACHE[key]
    else:
        loaded = trimesh.load(source_path)
        if isinstance(loaded, trimesh.Scene):
            if len(loaded.geometry) == 0:
                raise ValueError("3D Scene contains no valid geometry")
            try:
                geom = loaded.to_geometry()
                mesh = trimesh.util.concatenate(list(geom.values())) if isinstance(geom, dict) else geom
            except Exception:
                mesh = trimesh.util.concatenate(loaded.dump())
        else:
            mesh = loaded

        limits.validate_loaded_mesh(mesh)

        # Pre-convert visual colors once so we never repeat it during orbit
        if hasattr(mesh, "visual") and mesh.visual is not None:
            with contextlib.suppress(Exception):
                getattr(mesh, "visual", None) and setattr(mesh, "visual", mesh.visual.to_color())

        _MESH_CACHE[key] = mesh
        if len(_MESH_CACHE) > 16:
            _MESH_CACHE.pop(next(iter(_MESH_CACHE)))

    return render_3d_mesh(
        mesh=mesh,
        yaw_deg=config.yaw,
        pitch_deg=config.pitch,
        model_color=config.model_color,
        target_dimension=target_dimension,
    )
