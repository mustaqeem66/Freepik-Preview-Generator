#!/usr/bin/env python3
"""
Standalone, reproducible capability verification for PreviewGen.

This is the same set of renderer engines enforced by
``tests/integration/test_release_renderers_gate.py``, exposed as a single
command so a release audit can prove the advertised multi-format support on a
given machine *without* the full pytest toolchain or a frozen build.

Usage (run inside the project virtualenv)::

    python scripts/verify_environment.py

Exit code is ``0`` only when every **mandatory** engine and the optional
capabilities that are installed resolve cleanly. Missing mandatory pieces are
reported with the exact remediation command.

This script intentionally imports only the standard library plus the renderer
engines it is checking for; it never imports the GUI/webview stack.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# module -> human-readable capability it unlocks. These mirror
# MANDATORY_RENDERER_ENGINES in the release gate; a release is only releasable
# when every one of them is importable.
MANDATORY_ENGINES: dict[str, str] = {
    "PIL": "Raster (PNG/JPG/WebP/TIFF/BMP)",
    "resvg_py": "SVG / SVGZ vector rasterization",
    "psd_tools": "Photoshop (.psd) composite extraction",
    "trimesh": "3D models (OBJ/GLB/GLTF/STL/PLY)",
    "collada": "COLLADA (.dae) scene decoding",
    "lxml": "XML-based 3D model and CAD parsing",
    "networkx": "3MF/scene graph processing",
    "ezdxf": "AutoCAD DXF drawings",
    "cascadio": "CAD solids (STEP/STP/IGES/IGS)",
    "matplotlib": "DXF vector drawing rasterization",
    "fontTools": "WOFF / WOFF2 font decoding",
}

# module -> capability. Absence downgrades a documented feature but does not
# fail the mandatory gate.
OPTIONAL_ENGINES: dict[str, str] = {
    "olefile": "3ds Max (.max) embedded thumbnail extraction",
    "pypdfium2": "PDF vector rasterization",
    "brotli": "Compressed SVG (.svgz) reading",
}

REMEDIATION = "pip install --require-hashes -r requirements-lock.txt"


def _check_module(name: str) -> str | None:
    """Return ``None`` when the module imports cleanly, else the error text."""
    try:
        importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - report whatever the import raised
        return f"{type(exc).__name__}: {exc}"
    return None


def _frozen_artifact() -> Path | None:
    candidates = (
        PROJECT_ROOT / "dist" / "PreviewGen" / "PreviewGen",
        PROJECT_ROOT / "dist" / "PreviewGen" / "PreviewGen.exe",
        PROJECT_ROOT / "dist" / "PreviewGen.app" / "Contents" / "MacOS" / "PreviewGen",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    print(f"PreviewGen capability verification  (Python {sys.version.split()[0]})")
    print("-" * 64)

    failures: list[str] = []

    for name, capability in MANDATORY_ENGINES.items():
        error = _check_module(name)
        if error is None:
            print(f"  [PASS] {name:<12} {capability}")
        else:
            print(f"  [FAIL] {name:<12} {capability}  -> {error}")
            failures.append(name)

    for name, capability in OPTIONAL_ENGINES.items():
        error = _check_module(name)
        mark = "PASS" if error is None else "warn"
        note = "" if error is None else f"  (optional, missing: {capability})"
        print(f"  [{mark}] {name:<12} {capability}{note}")

    bundle = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if bundle.is_file():
        print(f"  [PASS] frontend bundle  {bundle.relative_to(PROJECT_ROOT)}")
    else:
        print("  [warn] frontend bundle  not built (run: cd frontend && npm ci && npm run build)")

    artifact = _frozen_artifact()
    if artifact is None:
        print("  [warn] frozen artifact  not built (run: pyinstaller --noconsole --name PreviewGen app.py)")
    else:
        print(f"  [PASS] frozen artifact  {artifact.relative_to(PROJECT_ROOT)}")

    print("-" * 64)
    if failures:
        print(f"RESULT: FAIL - missing mandatory engines: {', '.join(failures)}")
        print(f"Fix:   {REMEDIATION}")
        return 1

    print("RESULT: PASS - every mandatory renderer engine is available.")
    print("Next:  python -m pytest tests/ -q            # full suite")
    print("       <PreviewGen> --render-test-all --fixtures tests/fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
