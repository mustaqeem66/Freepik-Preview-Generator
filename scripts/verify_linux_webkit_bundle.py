#!/usr/bin/env python3
"""Verify that a frozen Linux artifact contains one complete WebKitGTK ABI.

The verifier accepts either a PyInstaller onedir directory or an AppImage. AppImages
are inspected with the runtime's supported ``--appimage-extract`` mode so the check
does not require FUSE or a mounted image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from previewgen.linux_webkit import (  # noqa: E402
    INJECTED_BUNDLE_DIRNAME,
    WEBKIT_MANIFEST_FILENAME,
    WEBKIT_MANIFEST_SCHEMA_VERSION,
)

_INJECTED_BUNDLE_FILENAME = "libwebkit2gtkinjectedbundle.so"
_FROZEN_WEBKIT_LIBRARY_NAMES = ("libwebkit2gtk-4.1.so.0", "libwebkit2gtk-4.0.so.0")
_HOST_GRAPHICS_LIBRARIES = ("libepoxy.so.0", "libgbm.so.1")


class VerificationError(RuntimeError):
    """Raised when a packaged artifact does not contain a complete WebKitGTK ABI."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_string(manifest: dict[str, Any], key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise VerificationError(f"WebKitGTK provenance manifest has no valid {key!r}")
    return value


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Could not read WebKitGTK provenance manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise VerificationError(f"WebKitGTK provenance manifest is not an object: {path}")
    if manifest.get("schema_version") != WEBKIT_MANIFEST_SCHEMA_VERSION:
        raise VerificationError(f"Unsupported WebKitGTK provenance manifest schema: {manifest.get('schema_version')!r}")
    return manifest


def _verify_tree(root: Path) -> Path:
    bundled_graphics = [path for library in _HOST_GRAPHICS_LIBRARIES for path in root.rglob(library) if path.is_file()]
    if bundled_graphics:
        names = ", ".join(sorted(path.name for path in bundled_graphics))
        raise VerificationError(
            f"Packaged artifact freezes graphics libraries; graphics libraries must be provided by the host: {names}"
        )

    bundles = [
        path
        for path in root.rglob(_INJECTED_BUNDLE_FILENAME)
        if path.is_file() and path.parent.name == INJECTED_BUNDLE_DIRNAME
    ]
    if not bundles:
        raise VerificationError(
            f"Packaged artifact is missing {_INJECTED_BUNDLE_FILENAME} in "
            f"the required {INJECTED_BUNDLE_DIRNAME}/ directory"
        )

    manifests = [
        path
        for path in root.rglob(WEBKIT_MANIFEST_FILENAME)
        if path.is_file() and path.parent.name == INJECTED_BUNDLE_DIRNAME
    ]
    if not manifests:
        raise VerificationError(
            f"Packaged artifact is missing {WEBKIT_MANIFEST_FILENAME} in "
            f"the required {INJECTED_BUNDLE_DIRNAME}/ directory"
        )
    if len(manifests) != 1:
        raise VerificationError(f"Packaged artifact contains multiple WebKitGTK provenance manifests: {manifests}")

    manifest_path = manifests[0]
    manifest = _load_manifest(manifest_path)
    api_version = _require_string(manifest, "api_version")
    package_name = _require_string(manifest, "package_name")
    _require_string(manifest, "package_version")
    library_filename = _require_string(manifest, "library_filename")
    library_checksum = _require_string(manifest, "library_sha256")
    bundle_filename = _require_string(manifest, "injected_bundle_filename")
    bundle_checksum = _require_string(manifest, "injected_bundle_sha256")
    needed = manifest.get("injected_bundle_needed")
    if not isinstance(needed, list) or not all(isinstance(item, str) for item in needed):
        raise VerificationError("WebKitGTK provenance manifest has no valid injected bundle dependency list")

    expected_library = f"libwebkit2gtk-{api_version}.so.0"
    expected_package = f"libwebkit2gtk-{api_version}-0"
    if package_name != expected_package:
        raise VerificationError(
            f"WebKitGTK provenance manifest package name {package_name!r} does not match API {api_version!r}"
        )
    if library_filename != expected_library or library_filename not in _FROZEN_WEBKIT_LIBRARY_NAMES:
        raise VerificationError(f"WebKitGTK provenance manifest names an invalid frozen library: {library_filename!r}")
    if bundle_filename != _INJECTED_BUNDLE_FILENAME:
        raise VerificationError(f"WebKitGTK provenance manifest names an invalid injected bundle: {bundle_filename!r}")
    if library_filename not in needed:
        raise VerificationError(f"WebKitGTK injected bundle does not declare the frozen library {library_filename!r}")

    libraries = [path for path in root.rglob(library_filename) if path.is_file()]
    if not libraries:
        raise VerificationError(f"Packaged artifact is missing the frozen WebKitGTK library ({library_filename})")
    if len(libraries) != 1:
        raise VerificationError(f"Packaged artifact contains multiple copies of {library_filename}: {libraries}")
    if _sha256(libraries[0]) != library_checksum:
        raise VerificationError("Packaged WebKitGTK library checksum does not match its provenance manifest")

    bundle_path = manifest_path.parent / bundle_filename
    if not bundle_path.is_file():
        raise VerificationError(
            f"Packaged artifact is missing {_INJECTED_BUNDLE_FILENAME} in "
            f"the required {INJECTED_BUNDLE_DIRNAME}/ directory"
        )
    if _sha256(bundle_path) != bundle_checksum:
        raise VerificationError("Packaged WebKitGTK injected bundle checksum does not match its provenance manifest")
    return bundle_path


def verify_linux_webkit_bundle(artifact: Path) -> Path:
    """Verify an onedir or AppImage and return the bundled injected-bundle path."""
    artifact = artifact.resolve()
    if artifact.is_dir():
        return _verify_tree(artifact)
    if not artifact.is_file():
        raise VerificationError(f"Packaged artifact does not exist: {artifact}")

    with tempfile.TemporaryDirectory(prefix="previewgen-appimage-") as temp_dir:
        extraction = subprocess.run(
            [str(artifact), "--appimage-extract"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if extraction.returncode != 0:
            detail = extraction.stderr.strip() or extraction.stdout.strip()
            raise VerificationError(f"Could not extract AppImage {artifact}: {detail}")

        extracted_root = Path(temp_dir) / "squashfs-root"
        if not extracted_root.is_dir():
            raise VerificationError(f"AppImage extraction did not create squashfs-root: {artifact}")
        return _verify_tree(extracted_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="PyInstaller onedir directory or AppImage file")
    args = parser.parse_args(argv)

    try:
        bundle = verify_linux_webkit_bundle(args.artifact)
    except VerificationError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1

    print(f"Verified matching injected bundle: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
