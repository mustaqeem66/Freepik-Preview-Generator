#!/usr/bin/env python3
"""Verify that a frozen Linux artifact contains one complete WebKitGTK ABI.

The verifier accepts either a PyInstaller onedir directory or an AppImage. AppImages
are inspected with the runtime's supported ``--appimage-extract`` mode so the check
does not require FUSE or a mounted image.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from previewgen.linux_webkit import INJECTED_BUNDLE_DIRNAME  # noqa: E402

_INJECTED_BUNDLE_FILENAME = "libwebkit2gtkinjectedbundle.so"
_FROZEN_WEBKIT_LIBRARY_NAMES = ("libwebkit2gtk-4.1.so.0", "libwebkit2gtk-4.0.so.0")


class VerificationError(RuntimeError):
    """Raised when a packaged artifact does not contain a complete WebKitGTK ABI."""


def _verify_tree(root: Path) -> Path:
    frozen_libraries = [
        path for library_name in _FROZEN_WEBKIT_LIBRARY_NAMES for path in root.rglob(library_name) if path.is_file()
    ]
    if not frozen_libraries:
        expected = " or ".join(_FROZEN_WEBKIT_LIBRARY_NAMES)
        raise VerificationError(f"Packaged artifact is missing the frozen WebKitGTK library ({expected})")

    injected_bundles = [
        path
        for path in root.rglob(_INJECTED_BUNDLE_FILENAME)
        if path.is_file() and path.parent.name == INJECTED_BUNDLE_DIRNAME
    ]
    if not injected_bundles:
        raise VerificationError(
            f"Packaged artifact is missing {_INJECTED_BUNDLE_FILENAME} in "
            f"the required {INJECTED_BUNDLE_DIRNAME}/ directory"
        )

    return injected_bundles[0]


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
