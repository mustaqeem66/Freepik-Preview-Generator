"""
PreviewGen 3D Mesh Renderer
Software-renders triangle meshes (.obj, .glb, .gltf, .stl, .ply, .3mf, .dae,
.blend) to transparent RGBA images from any yaw/pitch angle.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from previewgen import limits, proc
from previewgen.config import PreviewConfig
from previewgen.renderers.proprietary import extract_blend_thumbnail

_MESH_CACHE: dict[tuple[str, float], Any] = {}

# STL and 3MF (and CAD kernels) store geometry Z-up; glTF/OBJ/DAE are Y-up.
_Z_UP_EXTENSIONS = frozenset({".stl", ".3mf"})

# Above this many visible triangles, subpixel triangles are splatted in one
# vectorized pass instead of costing a per-triangle polygon call.
_SPLAT_THRESHOLD = 500_000


def _splat_subpixel_triangles(flat_rgba, triangles, colors, width: int, height: int) -> None:
    """Paint depth-ordered 2x2 splats for triangles smaller than a pixel.

    Triangles arrive far-to-near, so for overlapping pixels the nearest splat
    wins. The 2x2 footprint closes seams between neighbouring subpixel faces.
    """
    import numpy as np

    if len(triangles) == 0:
        return
    centre_x = np.rint(triangles[:, :, 0].mean(axis=1)).astype(np.int64)
    centre_y = np.rint(triangles[:, :, 1].mean(axis=1)).astype(np.int64)

    # One pass per footprint pixel: stable sort keeps the far-to-near input
    # order, so the last occurrence of a pixel is its nearest splat.
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        x = centre_x + dx
        y = centre_y + dy
        inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
        if not inside.any():
            continue
        pixel_id = y[inside] * width + x[inside]
        splat_color = colors[inside]
        order = np.argsort(pixel_id, kind="stable")
        pixel_id = pixel_id[order]
        splat_color = splat_color[order]
        keep = np.ones(len(pixel_id), dtype=bool)
        keep[:-1] = pixel_id[1:] != pixel_id[:-1]
        flat_rgba[pixel_id[keep], :3] = splat_color[keep, :3]
        flat_rgba[pixel_id[keep], 3] = 255


def _safe_face_colors(mesh, face_count: int):
    """Return per-face RGB colors or ``None``, never trusting trimesh's lazy
    ``face_colors`` property: for malformed visuals it raises IndexError rather
    than returning a wrong-length array."""
    import numpy as np

    visual = getattr(mesh, "visual", None)
    if visual is None or not getattr(visual, "defined", False):
        return None
    try:
        colors = np.asarray(visual.face_colors)
    except Exception:
        return None
    if colors.ndim == 1 and colors.size in (3, 4):
        return np.tile(colors[:3], (face_count, 1))
    if colors.ndim == 2 and colors.shape[0] == face_count and colors.shape[1] >= 3:
        return colors[:, :3]
    return None


def _normalize_visuals(mesh) -> None:
    """Rebuild the mesh visual as colorable per-face/per-vertex data.

    ``TextureVisuals.to_color()`` hands back a lone ``(4,)`` RGBA for an
    untextured PBR material; assigning that to trimesh makes the lazy
    ``face_colors`` property index a 4-element array with every face index and
    raise IndexError, which used to abort the whole preview.
    """
    import numpy as np
    from trimesh.visual.color import ColorVisuals

    visual = getattr(mesh, "visual", None)
    if visual is None or not getattr(visual, "defined", False):
        return
    try:
        converted = visual.to_color() if hasattr(visual, "to_color") else visual

        vertex_colors = getattr(converted, "vertex_colors", None)
        if vertex_colors is not None:
            vertex_colors = np.asarray(vertex_colors)
            if vertex_colors.ndim == 1 and vertex_colors.size in (3, 4):
                vertex_colors = np.tile(vertex_colors[:3], (len(mesh.vertices), 1))
            if (
                vertex_colors.ndim != 2
                or vertex_colors.shape[0] != len(mesh.vertices)
                or vertex_colors.shape[1] < 3
            ):
                vertex_colors = None
            else:
                vertex_colors = vertex_colors[:, :3]

        face_colors = None
        n_faces = len(mesh.faces) if getattr(mesh, "faces", None) is not None else 0
        if n_faces:
            try:
                face_colors = np.asarray(converted.face_colors)
            except Exception:
                face_colors = None
            if face_colors is not None:
                if face_colors.ndim == 1 and face_colors.size in (3, 4):
                    face_colors = np.tile(face_colors[:3], (n_faces, 1))
                if (
                    face_colors.ndim != 2
                    or face_colors.shape[0] != n_faces
                    or face_colors.shape[1] < 3
                ):
                    face_colors = None
                else:
                    face_colors = face_colors[:, :3]

        mesh.visual = ColorVisuals(
            mesh=mesh, face_colors=face_colors, vertex_colors=vertex_colors
        )
    except Exception:
        # A visual we cannot normalize must not take the geometry down with it;
        # the renderer falls back to the configured model color.
        return


def _combine_scene_meshes(scene, trimesh):
    """Apply each node's materials before combining potentially mixed visuals.

    A late whole-scene conversion cannot recover TextureVisuals lost during
    trimesh concatenation. dump() also applies node transforms to each mesh.
    """
    try:
        parts = list(scene.dump())
    except Exception:
        geometry = scene.to_geometry()
        parts = list(geometry.values()) if isinstance(geometry, dict) else [geometry]
    if not parts:
        raise ValueError("3D Scene contains no valid geometry")
    for part in parts:
        _normalize_visuals(part)
    return trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]


def render_3d_mesh(
    mesh,
    yaw_deg: float = 45.0,
    pitch_deg: float = 30.0,
    model_color: tuple[int, int, int] = (120, 130, 160),
    target_dimension: int = 2400,
    z_up: bool = False,
) -> Image.Image:
    """Render a 3D mesh from any yaw/pitch angle to a transparent RGBA PIL Image."""
    import numpy as np

    if not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
        raise ValueError("3D mesh contains no vertices")

    raw_verts = np.asarray(mesh.vertices, dtype=float)
    if not np.isfinite(raw_verts).all():
        raise ValueError("3D mesh contains non-finite vertex coordinates")
    raw_faces = getattr(mesh, "faces", None)
    faces = np.asarray(raw_faces) if raw_faces is not None else np.zeros((0, 3), dtype=np.int64)

    # A multi-million-triangle asset is mostly subpixel at preview size. Render
    # it at a reduced internal resolution so most faces take the vectorized
    # splat path, then upscale; every face is still drawn and coverage is kept.
    render_dim = target_dimension
    if len(faces) > 2 * _SPLAT_THRESHOLD:
        render_dim = max(
            400,
            int(round(target_dimension * ((2 * _SPLAT_THRESHOLD) / len(faces)) ** 0.75)),
        )
        render_dim = min(render_dim, target_dimension)
    W, H = render_dim, render_dim

    # trimesh's area-weighted centroid walks every triangle (seconds on a
    # multi-million-face mesh); the vertex mean frames the model just as well.
    verts = raw_verts - raw_verts.mean(axis=0)
    norms = np.linalg.norm(verts, axis=1)
    max_radius = float(np.max(norms)) if len(norms) > 0 else 1.0
    if max_radius <= 0 or not np.isfinite(max_radius):
        raise ValueError("3D mesh has zero spatial extent")
    verts = verts / max_radius

    # Z-up sources (STL/3MF/CAD) are rotated into the renderer's Y-up frame.
    z_up_transform = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
    if z_up:
        verts = verts @ z_up_transform.T

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

    if len(faces) == 0:
        result_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(result_img)
        pt_col = (*model_color, 220)
        step = max(1, len(pts_2d) // 25_000)
        for pt in pts_2d[::step]:
            draw.ellipse([pt[0] - 2, pt[1] - 2, pt[0] + 2, pt[1] + 2], fill=pt_col)
        if not np.asarray(result_img)[:, :, 3].any():
            raise ValueError("3D point cloud rendered to an empty image")
        return result_img

    normals = (
        mesh.face_normals
        if hasattr(mesh, "face_normals") and mesh.face_normals is not None
        else np.zeros((len(faces), 3))
    )
    if z_up:
        normals = normals @ z_up_transform.T
    n_rot = np.nan_to_num(normals @ R.T, nan=0.0)
    # Visible face determination and depth sorting (Finding: Hardware acceleration & optimized vector raster)
    visible_mask = n_rot[:, 2] > -0.55
    vis_indices = np.where(visible_mask)[0]
    if len(vis_indices) == 0:
        # Open, single-sided surfaces viewed from behind: shade them two-sided
        # instead of returning a blank "successful" preview.
        vis_indices = np.arange(len(faces))

    z = v_rot[:, 2]
    face_z = (z[faces[:, 0]] + z[faces[:, 1]] + z[faces[:, 2]]) / 3.0
    vis_order = vis_indices[np.argsort(face_z[vis_indices])]

    # Every visible face is drawn. Striding (previously used to cap draw work)
    # dropped triangles and left holes in dense meshes, so the face-count limit
    # in config.MAX_3D_FACES is the only budget.
    light_dir = np.array([0.45, 0.65, 0.61])
    light_dir /= np.linalg.norm(light_dir)
    diffuse = np.nan_to_num(np.abs(n_rot[vis_order] @ light_dir) * 0.72, nan=0.0)
    ambient = 0.35
    intensity = np.clip(ambient + diffuse, 0.0, 1.0)

    face_colors = _safe_face_colors(mesh, len(faces))
    default_base = np.array(model_color, dtype=float)
    base_colors = face_colors[vis_order].astype(float) if face_colors is not None else default_base
    lit_colors = np.clip(intensity[:, None] * base_colors, 0, 255).astype(np.uint8)
    ordered_pts = pts_2d[faces[vis_order]]  # shape: (N, 3, 2)

    result_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    if len(vis_order) > _SPLAT_THRESHOLD:
        tri_min = ordered_pts.min(axis=1)
        tri_max = ordered_pts.max(axis=1)
        subpixel = ((tri_max[:, 0] - tri_min[:, 0]) * (tri_max[:, 1] - tri_min[:, 1])) <= 1.0
        if subpixel.any():
            flat_rgba = np.array(result_img).reshape(-1, 4)
            _splat_subpixel_triangles(
                flat_rgba, ordered_pts[subpixel], lit_colors[subpixel], W, H
            )
            result_img = Image.fromarray(flat_rgba.reshape(H, W, 4), "RGBA")
        draw_indices = np.flatnonzero(~subpixel)
    else:
        draw_indices = np.arange(len(vis_order))

    draw = ImageDraw.Draw(result_img)
    for i in draw_indices:
        draw.polygon(ordered_pts[i].reshape(-1).tolist(), fill=tuple(lit_colors[i]))

    if not np.asarray(result_img)[:, :, 3].any():
        raise ValueError("3D mesh rendered to an empty image")
    if render_dim != target_dimension:
        result_img = result_img.resize(
            (target_dimension, target_dimension), Image.Resampling.BILINEAR
        )
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
                    [
                        blender_bin, "-b",
                        # A .blend is untrusted input: its text blocks can carry
                        # startup handlers that execute the moment it loads.
                        "--disable-autoexec",
                        str(source_path), "-P", str(script_py),
                    ],
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
            mesh = _combine_scene_meshes(loaded, trimesh)
        else:
            mesh = loaded
            _normalize_visuals(mesh)

        limits.validate_loaded_mesh(mesh)

        _MESH_CACHE[key] = mesh
        if len(_MESH_CACHE) > 16:
            _MESH_CACHE.pop(next(iter(_MESH_CACHE)))

    return render_3d_mesh(
        mesh=mesh,
        yaw_deg=config.yaw,
        pitch_deg=config.pitch,
        model_color=config.model_color,
        target_dimension=target_dimension,
        z_up=ext in _Z_UP_EXTENSIONS,
    )
