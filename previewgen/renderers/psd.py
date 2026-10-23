"""
PreviewGen PSD Renderer
Extracts the flattened composite layer from Adobe Photoshop documents.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from PIL import Image


def _load_psd(source_path: Path) -> Image.Image:
    """Extract the composite layer with transparency from an Adobe Photoshop PSD file."""
    try:
        from psd_tools import PSDImage
    except ImportError as exc:
        raise RuntimeError(
            "psd-tools is required to process PSD files. Please install it with: pip install psd-tools"
        ) from exc

    psd = PSDImage.open(source_path)
    try:
        composite = psd.composite()
        if composite is None:
            raise ValueError("Could not extract composite transparency layer from PSD")
        return composite.convert("RGBA")
    finally:
        # The gallery worker is long-lived, so an unclosed document leaks its
        # layer data, file handles and mmap for every PSD preview it renders.
        closer = getattr(psd, "close", None)
        if callable(closer):
            with contextlib.suppress(Exception):
                closer()
