#!/usr/bin/env python3
"""Generate *synthetic* format smoke fixtures without modifying checked-in art.

These are deterministic parser/packaging smoke inputs, NOT app-exported samples
and never independent visual oracles. Strict fidelity remains fail-closed.

Usage:
  python scripts/generate_synthetic_renderer_matrix.py --output-dir local-fixtures
  python scripts/audit_renderer_matrix.py --manifest local-fixtures/renderer-samples.json \\
      --fixtures-dir local-fixtures --verify-fixtures --report local-fixtures/report.json
"""
from __future__ import annotations

import argparse
import base64
import gzip
import io
import json
import shutil
import sqlite3
import struct
import time
import zipfile
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BASE_FIXTURES = ROOT / "tests" / "fixtures"
SAMPLE_MANIFEST = BASE_FIXTURES / "renderer-samples.json"
MANIFEST_NAME = "renderer-samples.json"


def _art() -> Image.Image:
    image = Image.new("RGBA", (160, 128), (0, 0, 0, 0))
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x + y) * 3) % 256, 255)
    return image


def _image_bytes(image: Image.Image, format_name: str, **metadata: object) -> bytes:
    out = io.BytesIO()
    image.save(out, format=format_name, **metadata)
    return out.getvalue()


def _zip_bytes(*items: tuple[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in items:
            # ZipFile.writestr(name, ...) would embed the current wall clock.
            member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, payload)
    return out.getvalue()


def _gltf_triangle() -> bytes:
    vertices = struct.pack("<9f", -1, -1, 0, 1, -1, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = vertices + indices
    encoded = base64.b64encode(binary).decode("ascii")
    document = {
        "asset": {"version": "2.0", "generator": "PreviewGen synthetic smoke"},
        "buffers": [{"byteLength": len(binary),
                     "uri": "data:application/octet-stream;base64," + encoded}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vertices), "target": 34962},
            {"buffer": 0, "byteOffset": len(vertices), "byteLength": len(indices), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [-1, -1, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "nodes": [{"mesh": 0}], "scenes": [{"nodes": [0]}], "scene": 0,
    }
    return json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")


def synthetic_samples() -> dict[str, bytes]:
    art = _art()
    png = _image_bytes(art, "PNG")
    jpeg = _image_bytes(art.convert("RGB"), "JPEG")
    tiff = _image_bytes(art, "TIFF")
    brush = _zip_bytes(("QuickLook/Thumbnail.png", png))
    compressed_svg = gzip.compress(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="128">'
        b'<rect width="160" height="128" fill="#55aaff"/>'
        b'<circle cx="70" cy="60" r="45" fill="#fbc34d"/></svg>',
        mtime=0,
    )
    stl = (
        "solid test\\n"
        "facet normal 0 0 1\\nouter loop\\n"
        "vertex 0 0 0\\nvertex 1 0 0\\nvertex 0 1 0\\n"
        "endloop\\nendfacet\\nendsolid test\\n"
    ).replace("\\n", "\n").encode("ascii")
    ply = (
        b"ply\nformat ascii 1.0\nelement vertex 3\n"
        b"property float x\nproperty float y\nproperty float z\n"
        b"element face 1\nproperty list uchar int vertex_indices\nend_header\n"
        b"0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n"
    )
    # ABR V1 sample tip follows the same documented structure as
    # tests/unit/test_creator_formats.py, rather than imitating modern strokes.
    w, h = 48, 48
    header = struct.pack(">HH", 1, 1)
    bounds = struct.pack(">IHB4h4iHB", 0, 25, 1, 0, 0, h, w, 0, 0, h, w, 8, 0)
    brush_pixels = bytes(n % 256 for n in range(w * h))
    abr = header + struct.pack(">HI", 2, len(bounds) + len(brush_pixels)) + bounds + brush_pixels
    xmp = (
        b"<xmpGImg:image>" + base64.b64encode(jpeg) + b"</xmpGImg:image>"
    )
    return {
        "synthetic.jpeg": jpeg,
        "synthetic.bmp": _image_bytes(art.convert("RGB"), "BMP"),
        "synthetic.gif": _image_bytes(art.convert("RGB"), "GIF"),
        "synthetic.ico": _image_bytes(art.resize((64, 64)), "ICO"),
        "synthetic.webp": _image_bytes(art, "WEBP"),
        "synthetic.tif": tiff,
        "synthetic.tiff": tiff,
        "synthetic.svgz": compressed_svg,
        "synthetic.stl": stl,
        "synthetic.ply": ply,
        "synthetic.gltf": _gltf_triangle(),
        "synthetic.kra": _zip_bytes(("mergedimage.png", png)),
        "synthetic.procreate": _zip_bytes(("QuickLook/Thumbnail.png", png)),
        "synthetic.brush": brush,
        "synthetic.brushset": _zip_bytes(("Brushes/first.brush", brush)),
        "synthetic.f3d": _zip_bytes(("Thumbnail/preview.png", png)),
        "synthetic.indd": b"IN_DESIGN_SYNTHETIC_XMP " + xmp,
        "synthetic.abr": abr,
        "synthetic.ai": _image_bytes(
            art.convert("RGB"), "PDF",
            creationDate=time.gmtime(0), modDate=time.gmtime(0),
            title="Synthetic PDF-compatible Illustrator smoke",
        ),
    }


def generate(output: Path) -> dict[str, object]:
    output = output.resolve()
    if output == BASE_FIXTURES.resolve():
        raise ValueError("Refusing to overwrite the committed fixture directory")
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads(SAMPLE_MANIFEST.read_text(encoding="utf-8"))
    copied = []
    for item in original["samples"]:
        name = item["file"]
        # Never allow an unchecked manifest pathname to escape the target root.
        if Path(name).name != name:
            raise ValueError("Invalid bundled fixture name")
        shutil.copyfile(BASE_FIXTURES / name, output / name)
        copied.append(dict(item))
    additional = synthetic_samples()
    for name, payload in sorted(additional.items()):
        if name in {item["file"] for item in copied}:
            raise ValueError(f"Duplicate fixture filename: {name}")
        (output / name).write_bytes(payload)
    samples = copied + [
        {"file": name, "sourceApp": "PreviewGen deterministic synthetic smoke",
         "sourceVersion": "synthetic-v1; not a real application export"}
        for name in sorted(additional)
    ]
    from previewgen.renderers.capabilities import CAPABILITIES
    suffixes = {Path(item["file"]).suffix for item in samples}
    unknown = suffixes - (set(CAPABILITIES) - {".zip"})
    if unknown:
        raise ValueError(f"Unknown fixture extension: {sorted(unknown)}")
    if len(suffixes) < 25:
        raise AssertionError(f"Expected at least 25 synthetic+bundled format paths, got {len(suffixes)}")
    result = {
        "schemaVersion": 1,
        "description": "Synthetic smoke plus existing bundled samples: NOT source-app fidelity oracles.",
        "samples": samples,
    }
    (output / MANIFEST_NAME).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {"sampleFiles": len(samples), "uniqueExtensions": len(suffixes),
            "generatedFiles": len(additional), "manifest": str(output / MANIFEST_NAME)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Explicit local output directory; never uses the committed fixtures path")
    arguments = parser.parse_args()
    print(json.dumps(generate(arguments.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
