"""
PreviewGen Processor (backward-compatibility facade)

The implementation has been split into focused, domain-specific modules:

* :mod:`previewgen.config`    - constants, resource limits, ``PreviewConfig``
* :mod:`previewgen.renderers` - format loaders, compositor, render pipeline
* :mod:`previewgen.batch`     - ZIP extraction and the folder batch runner

Supported Public Surface (P0 / Finding 10):
-------------------------------------------
Only the following symbols constitute the supported public facade API:
    - ``PreviewConfig``
    - ``generate_file``
    - ``preview_jpeg_bytes``
    - ``process_folder``
    - ``safe_extract_zip``

Internal renderer loaders, tile helpers, and caches (_load_3d, _load_svg, _load_psd,
_MESH_CACHE, compose_preview, etc.) are internal implementation details. They are
deprecated for external consumers and scheduled for removal in PreviewGen v3.0.
"""
from __future__ import annotations

import warnings
from typing import Any

from previewgen.batch import process_folder, safe_extract_zip
from previewgen.config import PreviewConfig
from previewgen.renderers import generate_file, preview_jpeg_bytes

# Supported public API surface (Finding 10)
__all__ = [
    "PreviewConfig",
    "generate_file",
    "preview_jpeg_bytes",
    "process_folder",
    "safe_extract_zip",
]

_DEPRECATED_INTERNAL_EXPORTS = {
    "_MESH_CACHE",
    "_calculate_text_position",
    "_checker_tile",
    "_font",
    "_load_3d",
    "_load_cad_solid",
    "_load_dwg",
    "_load_dxf",
    "_load_f3d",
    "_load_max",
    "_load_maya",
    "_load_psd",
    "_load_svg",
    "compose_preview",
    "extract_blend_thumbnail",
    "extract_dwg_thumbnail",
    "extract_f3d_thumbnail",
    "extract_max_thumbnail",
    "extract_maya_thumbnail",
    "load_source_image",
    "make_background",
    "render_3d_mesh",
}


def __getattr__(name: str) -> Any:
    """Provide backward compatibility with explicit deprecation warnings for internal details."""
    if name in _DEPRECATED_INTERNAL_EXPORTS:
        warnings.warn(
            f"Accessing internal processor detail '{name}' via legacy facade is deprecated "
            "and scheduled for removal in PreviewGen v3.0. Import from 'previewgen.renderers' "
            "or use 'generate_file' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        import previewgen.renderers as _renderers

        return getattr(_renderers, name)

    if (
        name.startswith("MAX_")
        or name.startswith("SUPPORTED_")
        or name in ("CHECKER_DARK", "CHECKER_LIGHT", "DEFAULT_TEXT", "SOLID_COLOR")
    ):
        warnings.warn(
            f"Importing constant '{name}' from 'processor' is deprecated. "
            "Import from 'previewgen.config' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        import previewgen.config as _config

        return getattr(_config, name)

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
