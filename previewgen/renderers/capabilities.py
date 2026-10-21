"""Truthful static preview capability catalog, aligned with the loader dispatch.

A recognized suffix never promises universal decoding. Every registered
extension must have one explicit source strategy so future additions cannot
silently advertise unsupported native formats.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from previewgen.config import SUPPORTED_EXTENSIONS


@dataclass(frozen=True)
class FormatCapability:
    mode: str
    label: str
    engines: tuple[str, ...]
    caveat: str

    def public(self) -> dict[str, object]:
        return asdict(self)


CAPABILITIES: dict[str, FormatCapability] = {}


def _register(
    extensions: tuple[str, ...], mode: str, label: str,
    engines: tuple[str, ...], caveat: str,
) -> None:
    for ext in extensions:
        if ext in CAPABILITIES:
            raise ValueError(f"Duplicate format capability: {ext}")
        CAPABILITIES[ext] = FormatCapability(mode, label, engines, caveat)


_register(
    (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".ico", ".webp", ".tif", ".tiff"),
    "raster", "Raster image", ("PIL",),
    "Decodes supported raster frames; animated inputs use the first frame.",
)
_register(
    (".svg", ".svgz"), "vector", "SVG vector renderer", ("resvg_py",),
    "External SVG resources or unsupported SVG features may differ from the authoring application.",
)
_register(
    (".ai",), "conditional", "PDF-compatible Illustrator or embedded preview",
    ("pypdfium2", "PIL"),
    "Requires a PDF-compatible Illustrator save or usable embedded thumbnail.",
)
_register(
    (".eps",), "conditional", "EPS or embedded preview", ("PIL",),
    "Some EPS documents need an embedded thumbnail or a compatible PostScript engine.",
)
_register(
    (".psd",), "composite", "Photoshop flattened composite", ("psd_tools",),
    "Renders a composited image, not a fully editable layer-accurate PSD.",
)
_register(
    (".ttf", ".otf", ".woff", ".woff2"),
    "font", "Font specimen renderer", ("PIL", "fontTools"),
    "Renders a sample card; a usable font face and WOFF decompression support are required.",
)
_register(
    (".obj", ".glb", ".gltf", ".stl", ".ply", ".3mf"),
    "mesh", "Software mesh renderer", ("trimesh",),
    "Camera orbit is a rasterized mesh approximation; materials and animation can be flattened.",
)
_register(
    (".dae",), "mesh", "COLLADA mesh renderer", ("trimesh", "collada"),
    "Complex linked resources and scene transforms may not match the source application.",
)
_register(
    (".step", ".stp", ".iges", ".igs"),
    "cad", "CAD solid tessellation", ("cascadio", "trimesh"),
    "Converts solids to a mesh; fidelity depends on geometry and converter availability.",
)
_register(
    (".dxf",), "cad", "DXF drawing renderer", ("ezdxf", "matplotlib"),
    "2D modelspace drawing; external references and complex entities may be unsupported.",
)
_register(
    (".dwg",), "embedded", "Embedded DWG thumbnail", (),
    "No general DWG geometry decoder; requires a thumbnail stored by AutoCAD.",
)
_register(
    (".blend",), "external_fallback", "Blender thumbnail or local Blender render", (),
    "Requires an embedded thumbnail or an installed Blender binary; not universal live 3D orbit.",
)
_register(
    (".max",), "embedded", "3ds Max embedded thumbnail", ("olefile",),
    "Requires an embedded preview in a compatible MAX container; not a native 3ds Max scene decoder.",
)
_register(
    (".f3d",), "embedded", "Fusion 360 embedded thumbnail", (),
    "Requires a preview image inside the Fusion archive.",
)
_register(
    (".ma", ".mb"), "embedded", "Maya embedded thumbnail", (),
    "Requires a saved Maya swatch or preview image; not a Maya scene interpreter.",
)
_register(
    (".procreate", ".brush", ".brushset", ".kra"),
    "embedded", "Creator-app flattened/thumbnail image", (),
    "Requires an embedded composite, brush tip or thumbnail; compatibility varies with file version.",
)
_register(
    (".clip",), "embedded", "Clip Studio stored canvas preview", (),
    "Requires a compatible preview database; arbitrary native layers are not reconstructed.",
)
_register(
    (".afdesign", ".afphoto", ".afpub"),
    "embedded", "Affinity embedded PNG preview", (),
    "Requires an embedded PNG preview in a supported Affinity file layout.",
)
_register(
    (".indd",), "embedded", "InDesign XMP thumbnail", (),
    "Requires a saved XMP thumbnail, not a full InDesign page-layout renderer.",
)
_register(
    (".abr",), "sample", "Photoshop brush sample", (),
    "Brush parser renders a representative tip; not a full Photoshop brush stroke.",
)
_register(
    (".zip",), "container", "ZIP member discovery only", (),
    "ZIP is not a single preview image. Select its folder to scan supported members.",
)


def capability_for(path_or_extension: str | Path) -> FormatCapability | None:
    text = str(path_or_extension).lower()
    suffix = text if text.startswith(".") and "/" not in text and "\\" not in text else Path(text).suffix
    return CAPABILITIES.get(suffix)


def validate_registry() -> tuple[set[str], set[str]]:
    """Return (advertised-without-capability, catalog-not-advertised)."""
    advertised = set(SUPPORTED_EXTENSIONS)
    described = set(CAPABILITIES)
    return advertised - described, described - advertised
