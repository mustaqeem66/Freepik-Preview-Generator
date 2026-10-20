"""
PreviewGen CAD Renderers
Handles .dxf drawings, .dwg embedded thumbnails, and universal CAD solids
(.step, .stp, .iges, .igs) converted to meshes for 360° orbit previews.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from previewgen import limits
from previewgen.config import MAX_SOURCE_FILE_BYTES, PreviewConfig
from previewgen.renderers.mesh3d import _MESH_CACHE, render_3d_mesh


def _load_dxf(source_path: Path, target_dimension: int = 2400) -> Image.Image:
    """Render an AutoCAD .dxf drawing/mesh using ezdxf and matplotlib."""
    try:
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        from matplotlib.figure import Figure

        declared_size = source_path.stat().st_size
        if declared_size > MAX_SOURCE_FILE_BYTES:
            raise ValueError(
                f"DXF file size {declared_size} exceeds the supported limit"
            )
        doc = ezdxf.readfile(str(source_path))
        msp = doc.modelspace()
        limits.validate_dxf_entity_limits(doc)

        dpi = 150
        size_in = target_dimension / dpi
        fig = Figure(figsize=(size_in, size_in), dpi=dpi)
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))

        ctx = RenderContext(doc)
        backend = MatplotlibBackend(ax)
        frontend = Frontend(ctx, backend)
        frontend.draw_layout(msp, finalize=True)

        # ``draw_layout(finalize=True)`` lets the backend resize the figure to fit
        # the drawing extents (matplotlib's default 6.4in base -> ~960px at
        # 150dpi), discarding the size requested above. Re-assert the requested
        # longest edge while keeping the aspect ratio the backend established.
        cur_w, cur_h = fig.get_size_inches()
        longest = max(float(cur_w), float(cur_h))
        if longest > 0:
            scale = size_in / longest
            fig.set_size_inches(float(cur_w) * scale, float(cur_h) * scale)
        fig.set_dpi(dpi)

        buf = BytesIO()
        fig.savefig(buf, format="png", transparent=True, dpi=dpi)

        buf.seek(0)
        with Image.open(buf) as pil_img:
            pil_img.load()
            return pil_img.convert("RGBA")
    except ImportError as exc:
        raise RuntimeError(
            f"DXF renderer component not available (install ezdxf and matplotlib): {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not render DXF file: {exc}") from exc


def extract_dwg_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded BMP or PNG thumbnail from AutoCAD .dwg binary header."""
    import struct
    try:
        with open(path, "rb") as f:
            header = f.read(6)
            if not header.startswith(b"AC"):
                return None
            f.seek(0x0D)
            offset_val = struct.unpack("<i", f.read(4))[0]
            next_pos = 0x14 + offset_val
            f.seek(0, 2)
            file_end = f.tell()
            if next_pos >= file_end:
                return None
            f.seek(next_pos)
            byt_cnt_raw = f.read(1)
            if not byt_cnt_raw or byt_cnt_raw[0] <= 1:
                return None
            for _ in range(byt_cnt_raw[0]):
                code_raw = f.read(1)
                if not code_raw:
                    break
                code = code_raw[0]
                data = f.read(8)
                if len(data) < 8:
                    break
                img_start, img_size = struct.unpack("<ii", data)
                dir_pos = f.tell()
                try:
                    if code == 2 and img_start > 0 and (img_start + img_size) <= file_end:
                        f.seek(img_start)
                        info_header = f.read(img_size)
                        if len(info_header) >= 40:
                            bi_bits = struct.unpack("<H", info_header[14:16])[0]
                            bi_size = struct.unpack("<I", info_header[20:24])[0]
                            c_table = (4 * (2 ** bi_bits)) if bi_bits < 9 else 0
                            file_sz = max(54 + c_table + bi_size, 14 + len(info_header))
                            bmp_data = b"BM" + struct.pack("<IHHI", file_sz, 0, 0, 54 + c_table) + info_header
                            return limits.bounded_image_from_bytes(bmp_data, "DWG thumbnail")
                    elif code == 6 and img_start > 0 and (img_start + img_size) <= file_end:
                        f.seek(img_start)
                        png_data = f.read(img_size)
                        return limits.bounded_image_from_bytes(png_data, "DWG thumbnail")
                except Exception:
                    pass
                finally:
                    f.seek(dir_pos)
        return None
    except Exception:
        return None


def _load_dwg(source_path: Path) -> Image.Image:
    thumb = extract_dwg_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError(
        "This DWG file does not contain an embedded preview thumbnail. "
        "In AutoCAD, save with THUMBSIZE enabled, or export as DXF."
    )


def _load_cad_solid(source_path: Path, config: PreviewConfig, target_dimension: int = 2400) -> Image.Image:
    """Convert universal CAD solids (.step, .stp, .iges, .igs) into 3D meshes for 360° orbit preview."""
    try:
        source_path = Path(source_path).resolve()
        mtime = source_path.stat().st_mtime if source_path.exists() else 0.0
        key = (str(source_path), mtime)
        if key in _MESH_CACHE:
            mesh = _MESH_CACHE[key]
        else:
            import cascadio
            glb_bytes = cascadio.to_glb_bytes(source_path.read_bytes())
            import trimesh
            mesh = trimesh.load(BytesIO(glb_bytes), file_type="glb")
            if isinstance(mesh, trimesh.Scene):
                try:
                    geom = mesh.to_geometry()
                    mesh = trimesh.util.concatenate(list(geom.values())) if isinstance(geom, dict) else geom
                except Exception:
                    mesh = trimesh.util.concatenate(mesh.dump())
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
        )
    except ImportError as exc:
        raise RuntimeError(
            f"CAD solid renderer component not available (install cascadio and trimesh): {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not convert CAD solid to 3D mesh: {exc}") from exc
