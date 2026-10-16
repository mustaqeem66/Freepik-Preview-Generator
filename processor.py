from __future__ import annotations
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFont

CHECKER_LIGHT = (245, 245, 248, 255)
CHECKER_DARK = (200, 204, 212, 255)
SOLID_COLOR = (255, 255, 255)
DEFAULT_TEXT = "100% TRANSPARENT"
SUPPORTED_3D_EXTENSIONS: tuple[str, ...] = (
    ".glb",
    ".gltf",
    ".obj",
    ".stl",
    ".ply",
    ".3mf",
    ".dae",
    ".blend",
)
SUPPORTED_CAD_EXTENSIONS: tuple[str, ...] = (
    ".dxf",
    ".dwg",
    ".max",
    ".f3d",
    ".mb",
    ".ma",
    ".step",
    ".stp",
    ".iges",
    ".igs",
)
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".svg",
    ".svgz",
    ".psd",
    *SUPPORTED_3D_EXTENSIONS,
    *SUPPORTED_CAD_EXTENSIONS,
    ".zip",
)


@dataclass
class PreviewConfig:
    text: str = DEFAULT_TEXT
    position: str = "top-left"            # top-left, top-right, center, bottom-left, bottom-right, custom
    opacity: float = 0.9                  # 0.0 to 1.0 (text opacity)
    invert_triangles: bool = True         # True: Left Solid, Right Transparent; False: Left Transparent, Right Solid
    solid_color: tuple[int, int, int] = (255, 255, 255)  # RGB of solid triangle
    text_color: tuple[int, int, int] = (255, 255, 255)   # RGB of text fill
    has_outline: bool = True              # Enable/disable outline stroke
    outline_color: tuple[int, int, int] = (0, 0, 0)      # RGB of outline stroke
    outline_thickness: int = 2            # 1 (thin) to 5 (extra bold)
    font_scale: float = 1.0               # 0.5 to 2.0
    # 3D View Angle & Shading
    yaw: float = 45.0                     # degrees (horizontal rotation: 0 to 360)
    pitch: float = 30.0                   # degrees (vertical elevation: -85 to 85)
    model_color: tuple[int, int, int] = (120, 130, 160)  # default studio slate
    # Freeform Text Coordinates (0.0 to 1.0 ratio of canvas width / height)
    text_pos_x: float = 0.05
    text_pos_y: float = 0.05
    # Custom Logo / Icon Branding Overlay
    logo_path: str = ""                   # Path to logo/icon file (or empty for none)
    logo_scale: float = 1.0               # Logo scale multiplier (0.2 to 3.0)
    logo_opacity: float = 0.9             # Logo opacity (0.0 to 1.0)
    logo_pos_x: float = 0.88              # Logo horizontal position (0.0 to 1.0)
    logo_pos_y: float = 0.05              # Logo vertical position (0.0 to 1.0)
    # Custom Font Support
    font_path: str = ""                   # Path to custom .ttf/.otf font file
    overwrite_policy: str = "rename"      # rename, skip, overwrite

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None, strict: bool = False) -> PreviewConfig:
        """Strictly parse, validate, and sanitize config from JS API or external dict."""
        if not isinstance(mapping, dict):
            return cls()

        KNOWN_KEYS = {
            "text", "position", "opacity", "invertTriangles", "invert_triangles",
            "solidColor", "solid_color", "textColor", "text_color",
            "hasOutline", "has_outline", "outlineColor", "outline_color",
            "outlineThickness", "outline_thickness", "fontScale", "font_scale",
            "yaw", "pitch", "modelColor", "model_color",
            "textPosX", "text_pos_x", "textPosY", "text_pos_y",
            "logoPath", "logo_path", "logoScale", "logo_scale",
            "logoOpacity", "logo_opacity", "logoPosX", "logo_pos_x",
            "logoPosY", "logo_pos_y", "fontPath", "font_path",
            "overwritePolicy", "overwrite_policy", "theme", "inputFolder", "outputFolder", "sameFolder"
        }
        if strict:
            unknown = set(mapping.keys()) - KNOWN_KEYS
            if unknown:
                raise ValueError(f"Unknown configuration key(s): {', '.join(sorted(unknown))}")

        def _safe_float(val: Any, default: float, min_val: float, max_val: float) -> float:
            try:
                if val is None or val == "":
                    return default
                f = float(val)
                if not (f == f) or f == float("inf") or f == float("-inf"):  # NaN or Inf check
                    return default
                return max(min_val, min(max_val, f))
            except (ValueError, TypeError):
                return default

        def _safe_int(val: Any, default: int, min_val: int, max_val: int) -> int:
            try:
                if val is None or val == "":
                    return default
                i = int(round(float(val)))
                return max(min_val, min(max_val, i))
            except (ValueError, TypeError):
                return default

        def _safe_bool(val: Any, default: bool) -> bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(val)
            if isinstance(val, str):
                v = val.strip().lower()
                if v in ("true", "1", "yes", "y", "on"):
                    return True
                if v in ("false", "0", "no", "n", "off"):
                    return False
            return default

        def _safe_color(val: Any, default: tuple[int, int, int]) -> tuple[int, int, int]:
            if isinstance(val, (tuple, list)) and len(val) >= 3:
                try:
                    return (
                        max(0, min(255, int(val[0]))),
                        max(0, min(255, int(val[1]))),
                        max(0, min(255, int(val[2]))),
                    )
                except (ValueError, TypeError):
                    return default
            if isinstance(val, str):
                h = val.strip().lstrip("#")
                if len(h) == 3:
                    h = "".join(c * 2 for c in h)
                if len(h) == 6:
                    try:
                        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                    except ValueError:
                        return default
            return default

        def _safe_path(val: Any, allowed_exts: tuple[str, ...]) -> str:
            if not isinstance(val, str) or not val.strip():
                return ""
            clean = val.strip()
            try:
                p = Path(clean)
                if p.suffix.lower() in allowed_exts and p.is_file():
                    return str(p.resolve())
            except Exception:
                return ""
            return ""

        # Text with length limit (max 100 chars to prevent memory/render DOS)
        raw_text = mapping.get("text", DEFAULT_TEXT)
        text = str(raw_text)[:100] if raw_text is not None else DEFAULT_TEXT

        # Allowed position presets
        raw_pos = str(mapping.get("position", "custom")).strip().lower()
        valid_positions = {"top-left", "top-right", "center", "bottom-left", "bottom-right", "custom"}
        position = raw_pos if raw_pos in valid_positions else "custom"

        # Overwrite policy
        raw_policy = str(mapping.get("overwritePolicy") or mapping.get("overwrite_policy", "rename")).strip().lower()
        overwrite_policy = raw_policy if raw_policy in {"overwrite", "skip", "rename"} else "rename"

        # Opacity: supports 0.0-1.0 or 0-100 percent
        raw_opacity = mapping.get("opacity", 90)
        op_val = float(raw_opacity) if isinstance(raw_opacity, (int, float, str)) and str(raw_opacity).replace('.', '', 1).isdigit() else 90.0
        opacity = (op_val / 100.0) if op_val > 1.0 else op_val
        opacity = max(0.0, min(1.0, opacity))

        # Scale values (0.1 to 3.0)
        raw_font_scale = mapping.get("fontScale", mapping.get("font_scale", 100))
        fs_val = float(raw_font_scale) if isinstance(raw_font_scale, (int, float, str)) and str(raw_font_scale).replace('.', '', 1).isdigit() else 100.0
        font_scale = (fs_val / 100.0) if fs_val > 5.0 else fs_val
        font_scale = max(0.2, min(3.0, font_scale))

        raw_logo_scale = mapping.get("logoScale", mapping.get("logo_scale", 100))
        ls_val = float(raw_logo_scale) if isinstance(raw_logo_scale, (int, float, str)) and str(raw_logo_scale).replace('.', '', 1).isdigit() else 100.0
        logo_scale = (ls_val / 100.0) if ls_val > 5.0 else ls_val
        logo_scale = max(0.2, min(3.0, logo_scale))

        raw_logo_op = mapping.get("logoOpacity", mapping.get("logo_opacity", 90))
        lop_val = float(raw_logo_op) if isinstance(raw_logo_op, (int, float, str)) and str(raw_logo_op).replace('.', '', 1).isdigit() else 90.0
        logo_opacity = (lop_val / 100.0) if lop_val > 1.0 else lop_val
        logo_opacity = max(0.0, min(1.0, logo_opacity))

        # Coordinates: 0.0 to 1.0 ratio
        def _to_ratio(val: Any, default: float) -> float:
            v = _safe_float(val, default * 100.0, 0.0, 100.0)
            return (v / 100.0) if v > 1.0 else max(0.0, min(1.0, v))

        text_pos_x = _to_ratio(mapping.get("textPosX", mapping.get("text_pos_x")), 0.05)
        text_pos_y = _to_ratio(mapping.get("textPosY", mapping.get("text_pos_y")), 0.05)
        logo_pos_x = _to_ratio(mapping.get("logoPosX", mapping.get("logo_pos_x")), 0.88)
        logo_pos_y = _to_ratio(mapping.get("logoPosY", mapping.get("logo_pos_y")), 0.05)

        # 3D Yaw & Pitch
        yaw = _safe_float(mapping.get("yaw"), 45.0, -360.0, 360.0) % 360.0
        pitch = _safe_float(mapping.get("pitch"), 30.0, -85.0, 85.0)

        # Validated paths
        logo_path = _safe_path(
            mapping.get("logoPath", mapping.get("logo_path")),
            (".png", ".webp", ".svg", ".ico", ".jpg", ".jpeg"),
        )
        font_path = _safe_path(
            mapping.get("fontPath", mapping.get("font_path")),
            (".ttf", ".otf", ".woff", ".woff2"),
        )

        return cls(
            text=text,
            position=position,
            opacity=opacity,
            invert_triangles=_safe_bool(mapping.get("invertTriangles", mapping.get("invert_triangles")), True),
            solid_color=_safe_color(mapping.get("solidColor", mapping.get("solid_color")), (255, 255, 255)),
            text_color=_safe_color(mapping.get("textColor", mapping.get("text_color")), (255, 255, 255)),
            has_outline=_safe_bool(mapping.get("hasOutline", mapping.get("has_outline")), True),
            outline_color=_safe_color(mapping.get("outlineColor", mapping.get("outline_color")), (0, 0, 0)),
            outline_thickness=_safe_int(mapping.get("outlineThickness", mapping.get("outline_thickness")), 2, 1, 10),
            font_scale=font_scale,
            yaw=yaw,
            pitch=pitch,
            model_color=_safe_color(mapping.get("modelColor", mapping.get("model_color")), (120, 130, 160)),
            text_pos_x=text_pos_x,
            text_pos_y=text_pos_y,
            logo_path=logo_path,
            logo_scale=logo_scale,
            logo_opacity=logo_opacity,
            logo_pos_x=logo_pos_x,
            logo_pos_y=logo_pos_y,
            font_path=font_path,
            overwrite_policy=overwrite_policy,
        )


def _font(size: int, font_path: str = "") -> Any:
    if font_path and Path(font_path).is_file():
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            pass
    candidates: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows")
        fonts_dir = windir / "Fonts"
        for name in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "arial.ttf"):
            candidates.append(fonts_dir / name)
    elif sys.platform == "darwin":
        for p in (
            "/System/Library/Fonts/SFProDisplay-Bold.otf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/Library/Fonts/Arial Bold.ttf",
        ):
            candidates.append(Path(p))
    else:
        for p in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ):
            candidates.append(Path(p))

    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _checker_tile(size: int) -> Image.Image:
    tile = Image.new("RGBA", (size * 2, size * 2), CHECKER_LIGHT)
    draw = ImageDraw.Draw(tile)
    draw.rectangle((size, 0, size * 2 - 1, size - 1), fill=CHECKER_DARK)
    draw.rectangle((0, size, size - 1, size * 2 - 1), fill=CHECKER_DARK)
    return tile


def make_background(
    width: int,
    height: int,
    invert_triangles: bool = True,
    solid_color: tuple[int, int, int] = SOLID_COLOR,
) -> Image.Image:
    """Create two equal-area triangles divided from bottom-left to top-right.

    invert_triangles=True:  Left is solid color, Right is checkerboard (transparent).
    invert_triangles=False: Left is checkerboard, Right is solid color.
    """
    if width < 1 or height < 1:
        raise ValueError("Invalid image dimensions")

    checker_size = max(8, min(96, round(min(width, height) / 64)))
    tile = _checker_tile(checker_size)
    checker = Image.new("RGBA", (width, height), CHECKER_LIGHT)
    for y in range(0, height, tile.height):
        for x in range(0, width, tile.width):
            checker.paste(tile, (x, y))

    solid = Image.new("RGBA", (width, height), (*solid_color, 255))

    # Triangle mask for the upper-left half
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon(
        [(0, 0), (width - 1, 0), (0, height - 1)], fill=255
    )

    if invert_triangles:
        # Left half is solid color, right half is checkerboard
        background = checker.copy()
        background.paste(solid, (0, 0), mask)
    else:
        # Left half is checkerboard, right half is solid color
        background = solid.copy()
        background.paste(checker, (0, 0), mask)

    # Draw subtle separator line along diagonal with contrasting tone
    draw = ImageDraw.Draw(background)
    lum = solid_color[0] * 0.299 + solid_color[1] * 0.587 + solid_color[2] * 0.114
    sep_rgb = (225, 228, 232, 255) if lum > 120 else (80, 90, 105, 255)
    draw.line(
        [(0, height - 1), (width - 1, 0)],
        fill=sep_rgb,
        width=max(1, round(min(width, height) / 1000)),
    )
    return background


def _calculate_text_position(
    image_size: tuple[int, int],
    text_size: tuple[int, int],
    position: str = "top-left",
    object_bounds: tuple[int, int, int, int] | None = None,
) -> tuple[int, int]:
    width, height = image_size
    tw, th = text_size

    # Responsive padding proportional to resolution
    pad_x = max(24, min(140, round(width * 0.038)))
    pad_y = max(24, min(140, round(height * 0.038)))

    pos = position.lower().strip()
    if pos == "top-left":
        x = pad_x
        y = pad_y
    elif pos == "top-right":
        x = width - tw - pad_x
        y = pad_y
    elif pos == "bottom-left":
        x = pad_x
        y = height - th - pad_y
    elif pos == "bottom-right":
        x = width - tw - pad_x
        y = height - th - pad_y
    elif pos == "center":
        if object_bounds:
            left, top, right, bottom = object_bounds
            cx = (left + right) // 2
            cy = (top + bottom) // 2
        else:
            cx = width // 2
            cy = height // 2
        x = cx - tw // 2
        y = cy - th // 2
    else:
        x = pad_x
        y = pad_y

    x = max(10, min(width - tw - 10, x))
    y = max(10, min(height - th - 10, y))
    return x, y


def compose_preview(
    source: Image.Image,
    config: PreviewConfig | None = None,
    text: str | None = None,
    position: str = "top-left",
    opacity: float = 0.9,
    invert_triangles: bool = True,
) -> Image.Image:
    """Composite preview without crop, trim, resize, rotation, or distortion."""
    if config is None:
        actual_text = text if text is not None else DEFAULT_TEXT
        config = PreviewConfig(
            text=actual_text,
            position=position,
            opacity=opacity,
            invert_triangles=invert_triangles,
        )

    original = source.convert("RGBA")
    width, height = original.size
    alpha_min, alpha_max = original.getchannel("A").getextrema()
    if alpha_max == 0:
        raise ValueError("Image is completely transparent (empty canvas)")

    bg = make_background(
        width,
        height,
        invert_triangles=config.invert_triangles,
        solid_color=config.solid_color,
    )
    result = Image.alpha_composite(bg, original)

    # ── 1. Custom Logo / Icon Branding Overlay ──
    if config.logo_path and Path(config.logo_path).is_file():
        try:
            logo_file = Path(config.logo_path)
            logo_img = load_source_image(logo_file)
            base_dim = round(min(width, height) * 0.16 * max(0.2, min(3.0, config.logo_scale)))
            lw, lh = logo_img.size
            if max(lw, lh) > 0:
                ratio = base_dim / max(lw, lh)
                target_lw = max(16, round(lw * ratio))
                target_lh = max(16, round(lh * ratio))
                logo_scaled = logo_img.resize((target_lw, target_lh), Image.Resampling.LANCZOS)

                clamped_logo_op = max(0.05, min(1.0, config.logo_opacity))
                if clamped_logo_op < 0.99:
                    lr, lg, lb, la = logo_scaled.split()
                    la = la.point(lambda p: round(p * clamped_logo_op))
                    logo_scaled.putalpha(la)

                lx = max(0, min(width - target_lw, round((width - target_lw) * max(0.0, min(1.0, config.logo_pos_x)))))
                ly = max(0, min(height - target_lh, round((height - target_lh) * max(0.0, min(1.0, config.logo_pos_y)))))

                logo_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
                logo_layer.paste(logo_scaled, (lx, ly), logo_scaled)
                result = Image.alpha_composite(result, logo_layer)
        except Exception:
            pass

    # ── 2. Watermark Text Overlay ──
    label = config.text.strip()
    if label:
        base_font_size = round(min(width, height) * 0.038 * config.font_scale)
        font_size = max(14, min(240, base_font_size))
        font = _font(font_size, config.font_path)

        multiplier = max(0.5, config.outline_thickness / 2.0)
        stroke = max(1, round(font_size * 0.075 * multiplier)) if config.has_outline else 0

        draw_calc = ImageDraw.Draw(result)
        box = draw_calc.textbbox((0, 0), label, font=font, stroke_width=stroke)
        tw = box[2] - box[0]
        th = box[3] - box[1]

        # Use freeform position coordinates
        if config.position == "custom" or (config.text_pos_x != 0.05 or config.text_pos_y != 0.05):
            x = max(0, min(width - tw, round((width - tw) * max(0.0, min(1.0, config.text_pos_x)))))
            y = max(0, min(height - th, round((height - th) * max(0.0, min(1.0, config.text_pos_y)))))
        else:
            obj_bounds = original.getchannel("A").getbbox()
            x, y = _calculate_text_position(result.size, (int(tw), int(th)), config.position, obj_bounds)

        text_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
        t_draw = ImageDraw.Draw(text_layer)

        clamped_opacity = max(0.05, min(1.0, config.opacity))
        alpha_fill = round(255 * clamped_opacity)
        fill_color = (*config.text_color, alpha_fill)

        draw_x = x - box[0]
        draw_y = y - box[1]

        if config.has_outline:
            stroke_fill = (*config.outline_color, alpha_fill)
            t_draw.text(
                (draw_x, draw_y),
                label,
                font=font,
                fill=fill_color,
                stroke_width=stroke,
                stroke_fill=stroke_fill,
            )
        else:
            t_draw.text(
                (draw_x, draw_y),
                label,
                font=font,
                fill=fill_color,
            )

        result = Image.alpha_composite(result, text_layer)
    return result.convert("RGB")

def _load_svg(source_path: Path, max_dimension: int | None = None) -> Image.Image:
    """Rasterize an SVG/SVGZ vector file to an exact-resolution RGBA PIL image using resvg.
    Handles uncompressed .svg and gzip-compressed .svgz cleanly.
    Preserves exact declared width/height or viewBox dimensions for export.
    If vector canvas is small (e.g. 24x24 icons) and no max_dimension is passed,
    scales up proportionally to target marketplace resolution (2400px).
    If max_dimension is provided (UI preview mode), scales proportionally within that bound.
    """
    try:
        import gzip
        import resvg_py
        raw_bytes = source_path.read_bytes()
        if raw_bytes.startswith(b"\x1f\x8b") or source_path.suffix.lower() == ".svgz":
            svg_str = gzip.decompress(raw_bytes).decode("utf-8", errors="ignore")
        else:
            svg_str = raw_bytes.decode("utf-8", errors="ignore")

        png_bytes = resvg_py.svg_to_bytes(svg_str)
        with Image.open(BytesIO(png_bytes)) as pil_img:
            pil_img.load()
            img = pil_img.convert("RGBA")

        w, h = img.size
        if w <= 0 or h <= 0:
            raise ValueError(f"Indeterminate SVG dimensions: {w}x{h}")

        if max_dimension is not None and max(w, h) > max_dimension:
            ratio = max_dimension / max(w, h)
            tw = max(1, round(w * ratio))
            th = max(1, round(h * ratio))
            return img.resize((tw, th), Image.Resampling.LANCZOS)

        return img
    except Exception as exc:
        raise RuntimeError(f"Could not render SVG file '{source_path.name}': {exc}")

def _load_psd(source_path: Path) -> Image.Image:
    """Extract the composite layer with transparency from an Adobe Photoshop PSD file."""
    try:
        from psd_tools import PSDImage
    except ImportError:
        raise RuntimeError(
            "psd-tools is required to process PSD files. Please install it with: pip install psd-tools"
        )

    psd = PSDImage.open(source_path)
    composite = psd.composite()
    if composite is None:
        raise ValueError("Could not extract composite transparency layer from PSD")
    return composite.convert("RGBA")

def _load_dxf(source_path: Path, target_dimension: int = 2400) -> Image.Image:
    """Render an AutoCAD .dxf drawing/mesh using ezdxf and matplotlib."""
    try:
        import ezdxf
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        from matplotlib.figure import Figure

        doc = ezdxf.readfile(str(source_path))
        msp = doc.modelspace()

        dpi = 150
        size_in = max(4.0, min(16.0, target_dimension / dpi))
        fig = Figure(figsize=(size_in, size_in), dpi=dpi)
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))

        ctx = RenderContext(doc)
        backend = MatplotlibBackend(ax)
        frontend = Frontend(ctx, backend)
        frontend.draw_layout(msp, finalize=True)

        buf = BytesIO()
        fig.savefig(buf, format="png", transparent=True, dpi=dpi)

        buf.seek(0)
        with Image.open(buf) as pil_img:
            pil_img.load()
            return pil_img.convert("RGBA")
    except Exception as exc:
        raise RuntimeError(f"Could not render DXF file: {exc}")


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
                            with Image.open(BytesIO(bmp_data)) as img:
                                img.load()
                                return img.convert("RGBA")
                    elif code == 6 and img_start > 0 and (img_start + img_size) <= file_end:
                        f.seek(img_start)
                        png_data = f.read(img_size)
                        with Image.open(BytesIO(png_data)) as img:
                            img.load()
                            return img.convert("RGBA")
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


def extract_max_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded viewport thumbnail from Autodesk 3ds Max (.max) OLE files."""
    try:
        import olefile
        if not olefile.isOleFile(str(path)):
            return None
        with olefile.OleFileIO(str(path)) as ole:
            for sname in ole.listdir():
                s_lower = "/".join(sname).lower()
                if "thumbnail" in s_lower or "preview" in s_lower:
                    data = ole.openstream(sname).read()
                    png_idx = data.find(b"\x89PNG\r\n\x1a\n")
                    if png_idx >= 0:
                        with Image.open(BytesIO(data[png_idx:])) as img:
                            img.load()
                            return img.convert("RGBA")
                    bmp_idx = data.find(b"BM")
                    if bmp_idx >= 0:
                        with Image.open(BytesIO(data[bmp_idx:])) as img:
                            img.load()
                            return img.convert("RGBA")
            if ole.exists("\x05SummaryInformation"):
                stream = ole.openstream("\x05SummaryInformation").read()
                png_idx = stream.find(b"\x89PNG\r\n\x1a\n")
                if png_idx >= 0:
                    with Image.open(BytesIO(stream[png_idx:])) as img:
                        img.load()
                        return img.convert("RGBA")
                bmp_idx = stream.find(b"BM")
                if bmp_idx >= 0:
                    with Image.open(BytesIO(stream[bmp_idx:])) as img:
                        img.load()
                        return img.convert("RGBA")
        return None
    except Exception:
        return None


def _load_max(source_path: Path) -> Image.Image:
    thumb = extract_max_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError(
        "This 3ds Max file has no embedded viewport thumbnail. "
        "In 3ds Max, enable 'Save Preview' in File Preferences, or export to .obj / .glb."
    )


def extract_f3d_thumbnail(path: Path) -> Image.Image | None:
    """Extract pre-rendered high-res PNG thumbnail from Autodesk Fusion 360 (.f3d) archives."""
    import zipfile
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            for name in zf.namelist():
                if "thumbnail" in name.lower() and name.lower().endswith((".png", ".jpg", ".jpeg")):
                    data = zf.read(name)
                    with Image.open(BytesIO(data)) as img:
                        img.load()
                        return img.convert("RGBA")
        return None
    except Exception:
        return None


def _load_f3d(source_path: Path) -> Image.Image:
    thumb = extract_f3d_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError("Could not find embedded preview thumbnail in this Fusion 360 (.f3d) file.")


def extract_maya_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded swatch/thumbnail from Autodesk Maya (.mb, .ma) files."""
    try:
        ext = path.suffix.lower()
        if ext == ".ma":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for _ in range(500):
                    line = f.readline()
                    if not line:
                        break
                    if "thumbnail" in line.lower():
                        import base64
                        import re
                        m = re.search(r'["\']([A-Za-z0-9+/=]{100,})["\']', line)
                        if m:
                            try:
                                 raw = base64.b64decode(m.group(1))
                                 with Image.open(BytesIO(raw)) as img:
                                     img.load()
                                     return img.convert("RGBA")
                            except Exception:
                                pass
        elif ext == ".mb":
            with open(path, "rb") as f:
                header_data = f.read(512 * 1024)
                png_idx = header_data.find(b"\x89PNG\r\n\x1a\n")
                if png_idx >= 0:
                    with Image.open(BytesIO(header_data[png_idx:])) as img:
                        img.load()
                        return img.convert("RGBA")
                jpg_idx = header_data.find(b"\xff\xd8\xff")
                if jpg_idx >= 0:
                    with Image.open(BytesIO(header_data[jpg_idx:])) as img:
                        img.load()
                        return img.convert("RGBA")
        return None
    except Exception:
        return None


def _load_maya(source_path: Path) -> Image.Image:
    thumb = extract_maya_thumbnail(source_path)
    if thumb is not None:
        return thumb
    raise RuntimeError(
        "This Maya file has no embedded swatch thumbnail. "
        "In Maya, enable 'Save Thumbnail' in Scene Save Preferences, or export to .obj / .glb."
    )


_MESH_CACHE: dict[tuple[str, float], Any] = {}

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
                    if isinstance(geom, dict):
                        mesh = trimesh.util.concatenate(list(geom.values()))
                    else:
                        mesh = geom
                except Exception:
                    mesh = trimesh.util.concatenate(mesh.dump())
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
    except Exception as exc:
        raise RuntimeError(f"Could not convert CAD solid to 3D mesh: {exc}")


def load_source_image(
    source_path: Path,
    config: PreviewConfig | None = None,
    max_dimension: int | None = None,
) -> Image.Image:
    """Load an input file (2D images, PSD, 3D meshes, CAD files) into a verified RGBA PIL Image."""
    source_path = Path(source_path)
    ext = source_path.suffix.lower()

    if ext in (".svg", ".svgz"):
        return _load_svg(source_path, max_dimension=max_dimension)

    if ext == ".psd":
        return _load_psd(source_path)

    if ext == ".dxf":
        return _load_dxf(source_path, target_dimension=max_dimension or 2400)

    if ext == ".dwg":
        return _load_dwg(source_path)

    if ext == ".max":
        return _load_max(source_path)

    if ext == ".f3d":
        return _load_f3d(source_path)

    if ext in (".mb", ".ma"):
        return _load_maya(source_path)

    if ext in (".step", ".stp", ".iges", ".igs"):
        return _load_cad_solid(source_path, config or PreviewConfig(), target_dimension=max_dimension or 2400)

    if ext in SUPPORTED_3D_EXTENSIONS:
        return _load_3d(source_path, config or PreviewConfig(), target_dimension=max_dimension or 2400)
    # Standard raster formats (.png, .webp, .tif, .tiff)
    with Image.open(source_path) as img:
        if getattr(img, "is_animated", False):
            img.seek(0)
        img.load()
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img) or img

        if img.mode in ("I;16", "I;16L", "I;16B", "I"):
            import numpy as np
            arr = (np.array(img, dtype=np.float32) / 256.0).clip(0, 255).astype(np.uint8)
            return Image.fromarray(arr).convert("RGBA")
        if img.mode in ("CMYK", "YCbCr"):
            return img.convert("RGB").convert("RGBA")
        return img.convert("RGBA")
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

    normals = mesh.face_normals if hasattr(mesh, "face_normals") and mesh.face_normals is not None else np.zeros((len(mesh.faces), 3))
    n_rot = np.nan_to_num(normals @ R.T, nan=0.0)
    face_z = v_rot[mesh.faces].mean(axis=1)[:, 2]
    order = np.argsort(face_z)

    visible_mask = n_rot[:, 2] > -0.55
    visible_order = [idx for idx in order if visible_mask[idx]]

    # Optimization: subsample faces during fast live preview for heavy models
    if target_dimension <= 1000 and len(visible_order) > 25_000:
        stride = max(2, len(visible_order) // 20_000)
        visible_order = visible_order[::stride]

    light_dir = np.array([0.45, 0.65, 0.61])
    light_dir /= np.linalg.norm(light_dir)
    diffuse = np.nan_to_num(np.abs(n_rot @ light_dir) * 0.72, nan=0.0)
    ambient = 0.35
    intensity = np.nan_to_num(np.clip(ambient + diffuse, 0.0, 1.0), nan=float(ambient))

    has_face_colors = (
        hasattr(mesh, "visual")
        and hasattr(mesh.visual, "face_colors")
        and mesh.visual.face_colors is not None
        and len(mesh.visual.face_colors) == len(mesh.faces)
    )

    result_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(result_img)
    default_base = np.array(model_color, dtype=float)

    for idx in visible_order:
        face = mesh.faces[idx]
        if has_face_colors:
            base_c = mesh.visual.face_colors[idx][:3].astype(float)
        else:
            base_c = default_base

        lit_val = np.nan_to_num(base_c * intensity[idx], nan=0.0)
        lit = tuple(np.clip(lit_val, 0, 255).astype(int))
        poly = [(float(pts_2d[v][0]), float(pts_2d[v][1])) for v in face]
        draw.polygon(poly, fill=lit)

    return result_img


def extract_blend_thumbnail(path: Path) -> Image.Image | None:
    """Extract embedded preview thumbnail from a .blend file in pure Python without Blender."""
    import struct
    import gzip

    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:2] == b"\x1f\x8b":
                f.seek(0)
                gf = gzip.GzipFile(fileobj=f)
                head = gf.read(12)
                stream = gf
            else:
                stream = f

            if not head.startswith(b"BLENDER"):
                return None

            is_64_bit = (head[7:8] == b"-")
            is_big_endian = (head[8:9] == b"V")
            sizeof_bhead = 24 if is_64_bit else 20
            int_endian = ">i" if is_big_endian else "<i"

            REND = b"REND"
            TEST = b"TEST"

            while True:
                bhead = stream.read(sizeof_bhead)
                if len(bhead) < sizeof_bhead:
                    return None
                code = bhead[:4]
                length = struct.unpack(int_endian, bhead[4:8])[0]
                if code == REND:
                    stream.seek(length, 1)
                else:
                    break

            if code != TEST:
                return None

            dims = stream.read(8)
            if len(dims) < 8:
                return None
            w, h = struct.unpack(int_endian + "i", dims)
            length -= 8
            if length != w * h * 4 or w <= 0 or h <= 0:
                return None

            raw_rgba = stream.read(length)
            if len(raw_rgba) != length:
                return None

            img = Image.frombytes("RGBA", (w, h), raw_rgba)
            return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    except Exception:
        return None


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
        import subprocess
        import tempfile
        import sys

        blender_bin = shutil.which("blender")
        if not blender_bin and sys.platform == "win32":
            prog_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
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
                subprocess.run(
                    [blender_bin, "-b", "-Y", str(source_path), "-P", str(script_py)],
                    capture_output=True,
                    timeout=60,
                )
                if out_png.exists():
                    with Image.open(out_png) as img:
                        img.load()
                        return img.convert("RGBA")

        raise RuntimeError(
            "This .blend file has no embedded preview thumbnail. "
            "To preview it, either install Blender or export the model to .glb, .gltf, or .obj (which render natively with full 360° controls)!"
        )

    try:
        import trimesh
    except ImportError:
        raise RuntimeError("trimesh is required for 3D model preview generation. Run: pip install trimesh")

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
                if isinstance(geom, dict):
                    mesh = trimesh.util.concatenate(list(geom.values()))
                else:
                    mesh = geom
            except Exception:
                mesh = trimesh.util.concatenate(loaded.dump())
        else:
            mesh = loaded

        # Pre-convert visual colors once so we never repeat it during orbit
        if hasattr(mesh, "visual") and mesh.visual is not None:
            try:
                getattr(mesh, "visual", None) and setattr(mesh, "visual", mesh.visual.to_color())
            except Exception:
                pass

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


def generate_file(
    source_path: Path,
    output_path: Path,
    config: PreviewConfig | None = None,
    text: str | None = None,
) -> None:
    if config is None:
        config = PreviewConfig(text=text if text is not None else DEFAULT_TEXT)

    source = load_source_image(source_path, config)
    output = compose_preview(source, config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    import uuid
    temp_name = f".tmp_{output_path.stem}_{uuid.uuid4().hex[:8]}.jpg"
    temp_path = output_path.parent / temp_name
    try:
        output.save(temp_path, format="JPEG", quality=96, subsampling=0, optimize=True)
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)


def preview_jpeg_bytes(
    source_path: Path | str,
    config: PreviewConfig | None = None,
    text: str | None = None,
    max_dimension: int = 850,
) -> tuple[bytes, int, int]:
    source_path = Path(source_path)
    if config is None:
        config = PreviewConfig(text=text if text is not None else DEFAULT_TEXT)

    source = load_source_image(source_path, config, max_dimension=max_dimension)
    orig_w, orig_h = source.size
    if max(orig_w, orig_h) > max_dimension:
        ratio = max_dimension / max(orig_w, orig_h)
        tw = max(1, round(orig_w * ratio))
        th = max(1, round(orig_h * ratio))
        source = source.resize((tw, th), Image.Resampling.BILINEAR)

    preview = compose_preview(source, config)

    buffer = BytesIO()
    preview.save(buffer, format="JPEG", quality=85, subsampling=0)
    return buffer.getvalue(), orig_w, orig_h

MAX_ZIP_MEMBERS = 2_000
MAX_MEMBER_BYTES = 250 * 1024 * 1024       # 250 MB
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB
MAX_COMPRESSION_RATIO = 200
MAX_PATH_LENGTH = 240
MAX_PATH_DEPTH = 20


def safe_extract_zip(zip_path: Path | str, target_dir: Path | str) -> list[Path]:
    """
    Safely extract a ZIP archive into target_dir with strict Zip-Slip protection,
    resource limits, and path depth/length validation.
    Returns list of extracted file Paths.
    """
    import zipfile

    source = Path(zip_path)
    root = Path(target_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    extracted_files: list[Path] = []
    total_extracted_bytes = 0
    member_count = 0

    with zipfile.ZipFile(source, "r") as zf:
        infolist = zf.infolist()
        if len(infolist) > MAX_ZIP_MEMBERS:
            raise ValueError(f"Archive exceeds maximum member limit ({len(infolist)} > {MAX_ZIP_MEMBERS})")

        for member in infolist:
            member_count += 1
            if member_count > MAX_ZIP_MEMBERS:
                raise ValueError(f"Archive member count exceeded limit ({MAX_ZIP_MEMBERS})")

            if member.file_size > MAX_MEMBER_BYTES:
                raise ValueError(
                    f"Member '{member.filename}' uncompressed size {member.file_size} exceeds limit {MAX_MEMBER_BYTES}"
                )

            if member.compress_size > 0:
                ratio = member.file_size / member.compress_size
                if ratio > MAX_COMPRESSION_RATIO and member.file_size > 1_000_000:
                    raise ValueError(f"Suspicious compression ratio ({ratio:.1f}) in '{member.filename}'")

            parts = Path(member.filename).parts
            if member.filename.startswith(("/", "\\")) or ".." in parts:
                raise ValueError(f"Archive member escapes extraction root (Zip-Slip attempt): {member.filename}")

            if (
                member.is_dir()
                or any(p.startswith(".") and p not in (".", "..") or p == "__MACOSX" for p in parts)
                or member.filename.lower().endswith((".ds_store", "thumbs.db", "desktop.ini"))
            ):
                continue

            if len(member.filename) > MAX_PATH_LENGTH:
                raise ValueError(f"Path length exceeds {MAX_PATH_LENGTH} characters: {member.filename}")
            if len(parts) > MAX_PATH_DEPTH:
                raise ValueError(f"Path depth exceeds {MAX_PATH_DEPTH} levels: {member.filename}")

            target = (root / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Archive member escapes extraction root (Zip-Slip attempt): {member.filename}") from exc

            bytes_written = 0
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > MAX_MEMBER_BYTES:
                        raise ValueError(f"Member '{member.filename}' exceeded size limit during extraction")
                    dst.write(chunk)

            total_extracted_bytes += bytes_written
            if total_extracted_bytes > MAX_TOTAL_BYTES:
                raise ValueError(f"Total archive size exceeds limit of {MAX_TOTAL_BYTES} bytes")

            extracted_files.append(target)

    return extracted_files
def process_folder(
    input_folder: Path,
    output_folder: Path,
    config: PreviewConfig,
    progress: Callable[[int, int, str], None],
    is_cancelled: Callable[[], bool],
) -> dict[str, Any]:
    raw_files = sorted(
        p for p in input_folder.rglob("*.*")
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTENSIONS
        and not any(
            part.startswith(".") and part not in (".", "..") or part == "__MACOSX"
            for part in p.relative_to(input_folder).parts
        )
    )
    if not raw_files:
        ext_list = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"No supported images ({ext_list}) found in the input folder")

    output_folder.mkdir(parents=True, exist_ok=True)
    success = 0
    failed = 0
    skipped = 0
    errors: list[str] = []
    import time
    start_time = time.time()

    work_items: list[tuple[Path, str]] = []
    allocated_names: set[str] = set()
    temp_dirs: list[Path] = []

    try:
        for src in raw_files:
            if src.suffix.lower() == ".zip":
                import tempfile
                zip_tmp = Path(tempfile.mkdtemp(prefix="previewgen_batch_zip_"))
                temp_dirs.append(zip_tmp)
                try:
                    safe_extract_zip(src, zip_tmp)
                    nested_zips = [nz for nz in zip_tmp.rglob("*.zip") if nz.is_file()]
                    for nz in nested_zips:
                        try:
                            safe_extract_zip(nz, nz.parent / nz.stem)
                        except Exception:
                            pass

                    inner_files = sorted(
                        p for p in zip_tmp.rglob("*.*")
                        if p.is_file()
                        and p.suffix.lower() in SUPPORTED_EXTENSIONS
                        and p.suffix.lower() != ".zip"
                        and not any(
                            part.startswith(".") and part not in (".", "..") or part == "__MACOSX"
                            for part in p.relative_to(zip_tmp).parts
                        )
                    )
                    if not inner_files:
                        failed += 1
                        errors.append(f"{src.name}: No supported assets inside archive")
                        continue

                    for inner in inner_files:
                        rel_parts = inner.relative_to(zip_tmp).parent.parts
                        slug = f"_{'_'.join(rel_parts)}" if rel_parts else ""
                        candidate_stem = f"{src.stem}{slug}_{inner.stem}"
                        counter = 1
                        out_name = f"{candidate_stem}.jpg"
                        while out_name.lower() in allocated_names:
                            out_name = f"{candidate_stem}_{inner.suffix.lstrip('.')}_{counter}.jpg"
                            counter += 1
                        allocated_names.add(out_name.lower())
                        work_items.append((inner, out_name))
                except Exception as exc:
                    failed += 1
                    errors.append(f"{src.name}: {exc}")
            else:
                rel_parts = src.relative_to(input_folder).parent.parts
                prefix = f"{'_'.join(rel_parts)}_" if rel_parts else ""
                candidate_stem = f"{prefix}{src.stem}"
                out_name = f"{candidate_stem}.jpg"
                counter = 1
                while out_name.lower() in allocated_names:
                    out_name = f"{candidate_stem}_{src.suffix.lstrip('.')}_{counter}.jpg"
                    counter += 1
                allocated_names.add(out_name.lower())
                work_items.append((src, out_name))

        total = max(1, len(work_items) + failed)
        completed = failed
        cancelled = False
        for item_path, out_name in work_items:
            if is_cancelled():
                cancelled = True
                break
            target_file = output_folder / out_name
            if target_file.exists():
                if config.overwrite_policy == "skip":
                    skipped += 1
                    completed += 1
                    progress(completed, total, f"Skipped (exists) {out_name}")
                    continue
                elif config.overwrite_policy == "rename":
                    r_count = 1
                    while target_file.exists():
                        target_file = output_folder / f"{target_file.stem}_copy{r_count}.jpg"
                        r_count += 1

            try:
                generate_file(item_path, target_file, config)
                success += 1
                status = f"Created {target_file.name}"
            except Exception as exc:
                failed += 1
                status = f"Failed {item_path.name}"
                errors.append(f"{item_path.name}: {exc}")

            completed += 1
            progress(completed, total, status)

    finally:
        for t in temp_dirs:
            shutil.rmtree(t, ignore_errors=True)

    duration = round(time.time() - start_time, 2)
    planned = len(work_items) + failed
    processed = success + failed + skipped
    remaining = max(0, planned - processed)
    return {
        "planned": planned,
        "processed": processed,
        "remaining": remaining,
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "cancelled": cancelled,
        "errors": errors,
        "duration": duration,
    }
