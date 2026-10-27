"""
PreviewGen Configuration
Canonical constants, resource limits, and the ``PreviewConfig`` value object.

This module is GUI-independent and dependency-light (Pillow only, for the
decompression-bomb limit) so it can be imported by renderers, the batch runner,
the settings layer, and tests without pulling in the GUI runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

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
SUPPORTED_VECTOR_EXTENSIONS: tuple[str, ...] = (
    ".svg",
    ".svgz",
    ".ai",
    ".eps",
)
SUPPORTED_CREATOR_EXTENSIONS: tuple[str, ...] = (
    ".procreate",
    ".brush",
    ".brushset",
    ".clip",
    ".kra",
    ".afdesign",
    ".afphoto",
    ".afpub",
    ".indd",
    ".abr",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
)
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".ico",
    ".webp",
    ".tif",
    ".tiff",
    ".psd",
    *SUPPORTED_VECTOR_EXTENSIONS,
    *SUPPORTED_CREATOR_EXTENSIONS,
    *SUPPORTED_3D_EXTENSIONS,
    *SUPPORTED_CAD_EXTENSIONS,
    ".zip",
)

MAX_SOURCE_FILE_BYTES: int = 500 * 1024 * 1024   # 500 MB max input asset
MAX_IMAGE_PIXELS: int = 100_000_000              # 100 MP decompression bomb safety
DEFAULT_RENDER_DIMENSION: int = 2400             # longest edge for re-rendered formats
MAX_EXPORT_DIMENSION: int = 8192                 # longest edge the user may request
MIN_RENDER_OUTPUT_COLORS: int = 8                # a real render must have >1 colour
MAX_SVG_DIMENSION: int = 16_384                  # 16K max vector bounds
MAX_PSD_DIMENSION: int = 30_000                  # 30K max layered canvas
MAX_3D_FACES: int = 2_000_000                    # 2M max polygonal faces for real-time orbit
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# Pre-parse resource limits. These are validated *before* the expensive parse /
# allocation step so a hostile or oversized asset is rejected up front rather
# than after it has already exhausted memory.
MAX_RASTER_DIMENSION: int = 20_000               # per-side raster cap (header only)
MAX_PSD_LAYERS: int = 2_000                      # max PSD layer records
MAX_3D_VERTICES: int = 5_000_000                 # max mesh vertices
MAX_CAD_ENTITIES: int = 500_000                  # max DXF modelspace entities
MAX_EMBEDDED_THUMBNAIL_BYTES: int = 64 * 1024 * 1024   # 64 MB embedded thumbnail
MAX_SVG_DECOMPRESSED_BYTES: int = 64 * 1024 * 1024     # 64 MB decompressed SVGZ
MAX_RENDERER_MEMORY_BYTES: int = 4 * 1024 * 1024 * 1024  # 4 GiB child-process ceiling
MIN_FREE_DISK_BYTES: int = 64 * 1024 * 1024      # keep at least 64 MB free
EXPECTED_OUTPUT_MAX_BYTES: int = 2400 * 2400 * 4  # upper bound for a composed JPEG


# ZIP extraction limits
MAX_ZIP_MEMBERS = 2_000
MAX_MEMBER_BYTES = 250 * 1024 * 1024       # 250 MB
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB
MAX_COMPRESSION_RATIO = 200
MAX_PATH_LENGTH = 240
MAX_PATH_DEPTH = 20

# Batch report naming and retention
REPORT_PREFIX = "previewgen-report-"
REPORT_LATEST = "previewgen-report-latest.json"
REPORT_RETENTION = 20                       # keep the N most recent report pairs

# Batch discovery bounds: defensive limits so a pathological input tree (slow
# network share, cloud-backed folder, symlink cycle, permission-heavy directory)
# can never hang cancellation or exhaust memory. Discovery streams lazily and
# checks the cancellation predicate at every directory and file.
DISCOVERY_MAX_FILES = 100_000
DISCOVERY_MAX_DIRECTORIES = 50_000
DISCOVERY_TIMEOUT_SECONDS = 120.0
DISCOVERY_MAX_DEPTH = 15


@dataclass
class PreviewConfig:
    text: str = DEFAULT_TEXT
    position: str = "top-left"            # top-left, top-right, center, bottom-left, bottom-right, custom
    opacity: float = 0.9                  # 0.0 to 1.0 (text opacity)
    auto_frame: bool = False               # off preserves historical exports
    animation_contact_sheet: bool = False  # GIF/WebP only, off keeps first frame
    brushset_contact_sheet: bool = False    # .brushset only, existing first tip unchanged
    frame_margin: float = 0.08             # fraction per side, constrained 0.00–0.25
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
    # Export resolution (longest edge, in pixels). 0 = native / renderer default.
    # Resizable assets (vector / re-rendered formats) may scale up to
    # ``MAX_EXPORT_DIMENSION``; fixed-bitmap assets only ever downscale.
    output_width: int = 0
    output_height: int = 0

    @classmethod
    def from_mapping(
        cls,
        mapping: dict[str, Any] | None,
        mode: str = "preview",
        strict: bool | None = None,
    ) -> PreviewConfig:
        """
        Parse and validate configuration dictionary.
        Modes:
          - 'preview': Forgiving and sanitized for interactive live canvas.
          - 'strict-export': Rejects invalid types, malformed colors, unknown keys, or invalid paths with ValueError.
        """
        if not isinstance(mapping, dict):
            if mode == "strict-export" or strict is True:
                raise ValueError("Configuration must be a dictionary")
            return cls()

        is_strict = mode == "strict-export" or strict is True

        KNOWN_KEYS = {
            "text", "position", "opacity", "invertTriangles", "invert_triangles",
            "solidColor", "solid_color", "textColor", "text_color",
            "autoFrame", "auto_frame", "frameMargin", "frame_margin",
            "animationContactSheet", "animation_contact_sheet",
            "brushsetContactSheet", "brushset_contact_sheet",
            "hasOutline", "has_outline", "outlineColor", "outline_color",
            "outlineThickness", "outline_thickness", "fontScale", "font_scale",
            "yaw", "pitch", "modelColor", "model_color",
            "textPosX", "text_pos_x", "textPosY", "text_pos_y",
            "logoPath", "logo_path", "logoScale", "logo_scale",
            "logoOpacity", "logo_opacity", "logoPosX", "logo_pos_x",
            "logoPosY", "logo_pos_y", "fontPath", "font_path",
            "overwritePolicy", "overwrite_policy", "theme", "inputFolder", "outputFolder", "sameFolder",
            "desktopNotifications",
            "outputWidth", "output_width", "outputHeight", "output_height",
        }
        if is_strict:
            unknown = set(mapping.keys()) - KNOWN_KEYS
            if unknown:
                raise ValueError(f"Unknown configuration key(s): {', '.join(sorted(unknown))}")
        def _safe_float(val: Any, default: float, min_val: float, max_val: float, field_name: str = "") -> float:
            try:
                if val is None or val == "":
                    return default
                f = float(val)
                if f != f or f == float("inf") or f == float("-inf"):
                    if is_strict:
                        raise ValueError(f"Invalid non-finite float value for {field_name}")
                    return default
                if is_strict and (f < min_val or f > max_val):
                    raise ValueError(f"Value for {field_name} out of bounds [{min_val}, {max_val}]: {f}")
                return max(min_val, min(max_val, f))
            except (ValueError, TypeError) as exc:
                if is_strict:
                    raise ValueError(f"Invalid float for {field_name}: {exc}") from exc
                return default

        def _safe_int(val: Any, default: int, min_val: int, max_val: int, field_name: str = "") -> int:
            try:
                if val is None or val == "":
                    return default
                i = int(round(float(val)))
                if is_strict and (i < min_val or i > max_val):
                    raise ValueError(f"Value for {field_name} out of bounds [{min_val}, {max_val}]: {i}")
                return max(min_val, min(max_val, i))
            except (ValueError, TypeError, OverflowError) as exc:
                if is_strict:
                    raise ValueError(f"Invalid integer for {field_name}: {exc}") from exc
                return default

        def _safe_bool(val: Any, default: bool, field_name: str = "") -> bool:
            if val is None or val == "":
                return default
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
            if is_strict:
                raise ValueError(f"Invalid boolean value for {field_name}: {val!r}")
            return default
        def _safe_color(val: Any, default: tuple[int, int, int], field_name: str = "") -> tuple[int, int, int]:
            if val is None or val == "":
                return default
            if isinstance(val, (tuple, list)) and len(val) >= 3:
                try:
                    c = (
                        int(val[0]),
                        int(val[1]),
                        int(val[2]),
                    )
                    if is_strict and any(channel < 0 or channel > 255 for channel in c):
                        raise ValueError(f"RGB channel for {field_name} must be 0-255: {c}")
                    return (max(0, min(255, c[0])), max(0, min(255, c[1])), max(0, min(255, c[2])))
                except (ValueError, TypeError) as exc:
                    if is_strict:
                        raise ValueError(f"Invalid RGB color tuple for {field_name}: {val!r}") from exc
                    return default
            if isinstance(val, str):
                h = val.strip().lstrip("#")
                if len(h) == 3:
                    h = "".join(ch * 2 for ch in h)
                if len(h) == 6:
                    try:
                        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                    except ValueError as exc:
                        if is_strict:
                            raise ValueError(f"Invalid hex color for {field_name}: {val!r}") from exc
                        return default
            if is_strict:
                raise ValueError(f"Invalid color specification for {field_name}: {val!r}")
            return default

        def _safe_path(val: Any, allowed_exts: tuple[str, ...], field_name: str = "") -> str:
            if not isinstance(val, str) or not val.strip():
                return ""
            clean = val.strip()
            try:
                p = Path(clean)
                if p.suffix.lower() not in allowed_exts:
                    if is_strict:
                        raise ValueError(f"File extension for {field_name} not permitted: {p.suffix}")
                    return ""
                if not p.is_file():
                    if is_strict:
                        raise ValueError(f"Path for {field_name} does not exist: {clean}")
                    return ""
                return str(p.resolve())
            except Exception as exc:
                if is_strict:
                    raise ValueError(f"Invalid file path for {field_name}: {exc}") from exc
                return ""


        # Text with length limit (max 100 chars to prevent memory/render DOS)
        raw_text = mapping.get("text", DEFAULT_TEXT)
        text = str(raw_text)[:100] if raw_text is not None else DEFAULT_TEXT

        # Allowed position presets
        raw_pos = str(mapping.get("position", "custom")).strip().lower()
        valid_positions = {"top-left", "top-right", "center", "bottom-left", "bottom-right", "custom", "tiled"}
        position = raw_pos if raw_pos in valid_positions else "custom"

        # Overwrite policy
        raw_policy = str(mapping.get("overwritePolicy") or mapping.get("overwrite_policy", "rename")).strip().lower()
        overwrite_policy = raw_policy if raw_policy in {"overwrite", "skip", "rename"} else "rename"

        # Bridge values are percentages, including 0–1%; never infer units from
        # magnitude. Snake-case fields retain the dataclass's normalized units.
        opacity = _safe_float(mapping.get("opacity"), 90.0, 0.0, 100.0, "opacity") / 100.0

        def _ratio(camel: str, snake: str, default: float, low: float = 0.0, high: float = 1.0) -> float:
            if camel in mapping:
                return _safe_float(mapping[camel], default * 100, low * 100, high * 100, camel) / 100
            return _safe_float(mapping.get(snake), default, low, high, snake)

        font_scale = _ratio("fontScale", "font_scale", 1.0, 0.2, 3.0)
        logo_scale = _ratio("logoScale", "logo_scale", 1.0, 0.2, 3.0)
        logo_opacity = _ratio("logoOpacity", "logo_opacity", 0.9)
        text_pos_x = _ratio("textPosX", "text_pos_x", 0.05)
        text_pos_y = _ratio("textPosY", "text_pos_y", 0.05)
        logo_pos_x = _ratio("logoPosX", "logo_pos_x", 0.88)
        logo_pos_y = _ratio("logoPosY", "logo_pos_y", 0.05)

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
            auto_frame=_safe_bool(mapping.get("autoFrame", mapping.get("auto_frame")), False, "autoFrame"),
            animation_contact_sheet=_safe_bool(mapping.get("animationContactSheet", mapping.get("animation_contact_sheet")), False, "animationContactSheet"),
            brushset_contact_sheet=_safe_bool(mapping.get("brushsetContactSheet", mapping.get("brushset_contact_sheet")), False, "brushsetContactSheet"),
            frame_margin=_ratio("frameMargin", "frame_margin", 0.08, 0.0, 0.25),
            invert_triangles=_safe_bool(
                mapping.get("invertTriangles", mapping.get("invert_triangles")), True, "invertTriangles"
            ),
            solid_color=_safe_color(
                mapping.get("solidColor", mapping.get("solid_color")), (255, 255, 255), "solidColor"
            ),
            text_color=_safe_color(
                mapping.get("textColor", mapping.get("text_color")), (255, 255, 255), "textColor"
            ),
            has_outline=_safe_bool(mapping.get("hasOutline", mapping.get("has_outline")), True, "hasOutline"),
            outline_color=_safe_color(
                mapping.get("outlineColor", mapping.get("outline_color")), (0, 0, 0), "outlineColor"
            ),
            outline_thickness=_safe_int(
                mapping.get("outlineThickness", mapping.get("outline_thickness")), 2, 1, 10, "outlineThickness"
            ),
            font_scale=font_scale,
            yaw=yaw,
            pitch=pitch,
            model_color=_safe_color(
                mapping.get("modelColor", mapping.get("model_color")), (120, 130, 160), "modelColor"
            ),
            text_pos_x=text_pos_x,
            text_pos_y=text_pos_y,
            logo_path=logo_path,
            logo_scale=logo_scale,
            logo_opacity=logo_opacity,
            logo_pos_x=logo_pos_x,
            logo_pos_y=logo_pos_y,
            font_path=font_path,
            overwrite_policy=overwrite_policy,
            output_width=_safe_int(
                mapping.get("outputWidth", mapping.get("output_width")), 0, 0, MAX_EXPORT_DIMENSION, "outputWidth"
            ),
            output_height=_safe_int(
                mapping.get("outputHeight", mapping.get("output_height")), 0, 0, MAX_EXPORT_DIMENSION, "outputHeight"
            ),
        )
