"""Linux WebKitGTK runtime configuration.

A frozen PreviewGen application must use the WebKitGTK injected bundle that
matches its frozen WebKitGTK shared library. Source checkouts continue to use
the host's matching WebKitGTK installation.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

INJECTED_BUNDLE_ENV = "WEBKIT_INJECTED_BUNDLE_PATH"
INJECTED_BUNDLE_DIRNAME = "webkit_injected_bundle"
WEBKIT_MANIFEST_FILENAME = "webkit_manifest.json"
WEBKIT_MANIFEST_SCHEMA_VERSION = 1
_INJECTED_BUNDLE_FILENAME = "libwebkit2gtkinjectedbundle.so"
_NEEDED_LIBRARY = re.compile(r"\(NEEDED\).*\[([^]]+)]")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_elf_needed_libraries(path: Path) -> list[str]:
    """Return the shared libraries required by an ELF binary."""
    readelf = shutil.which("readelf")
    if readelf is None:
        raise RuntimeError("readelf is required to verify WebKitGTK binary provenance")
    result = subprocess.run(
        [readelf, "-d", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Could not inspect ELF dependencies for {path}: {detail}")
    needed = [match.group(1) for line in result.stdout.splitlines() if (match := _NEEDED_LIBRARY.search(line))]
    if not needed:
        raise RuntimeError(f"ELF dependency inspection found no NEEDED libraries in {path}")
    return needed


def read_dpkg_package_version(package_name: str) -> str:
    """Return the installed Debian package version for WebKitGTK provenance."""
    dpkg_query = shutil.which("dpkg-query")
    if dpkg_query is None:
        raise RuntimeError("dpkg-query is required to record WebKitGTK package provenance")
    result = subprocess.run(
        [dpkg_query, "-W", "-f=${Version}", package_name],
        capture_output=True,
        text=True,
        check=False,
    )
    version = result.stdout.strip()
    if result.returncode != 0 or not version:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Could not read WebKitGTK package version for {package_name}: {detail}")
    return version


def build_webkit_manifest(
    *,
    api_version: str,
    package_name: str,
    package_version: str,
    library_path: Path,
    injected_bundle_path: Path,
    injected_bundle_needed: list[str],
) -> dict[str, Any]:
    """Build the provenance record for one selected WebKitGTK ABI pair."""
    if api_version not in {"4.0", "4.1"}:
        raise ValueError(f"Unsupported WebKitGTK API version: {api_version}")
    if not package_name or not package_version:
        raise ValueError("WebKitGTK package provenance must include a package name and version")
    expected_library = f"libwebkit2gtk-{api_version}.so.0"
    if library_path.name != expected_library:
        raise ValueError(f"Expected {expected_library}, got {library_path.name}")
    if expected_library not in injected_bundle_needed:
        raise ValueError(f"Injected bundle does not declare {expected_library} as a dependency")
    return {
        "schema_version": WEBKIT_MANIFEST_SCHEMA_VERSION,
        "api_version": api_version,
        "package_name": package_name,
        "package_version": package_version,
        "library_filename": library_path.name,
        "library_sha256": _sha256(library_path),
        "injected_bundle_filename": injected_bundle_path.name,
        "injected_bundle_sha256": _sha256(injected_bundle_path),
        "injected_bundle_needed": injected_bundle_needed,
    }


def write_webkit_manifest(manifest: dict[str, Any]) -> Path:
    """Write a manifest to a temporary file for PyInstaller to collect."""
    directory = Path(tempfile.mkdtemp(prefix="previewgen_webkit_"))
    path = directory / WEBKIT_MANIFEST_FILENAME
    try:
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def configure_linux_webkit_runtime(
    resource_dir: Path,
    *,
    platform: str,
    environ: MutableMapping[str, str],
    frozen: bool,
) -> Path | None:
    """Configure a frozen Linux app to use its bundled WebKit injected bundle.

    Returns the bundle directory on Linux frozen builds and ``None`` for source
    checkouts and other platforms. A frozen Linux build fails closed when the
    matching injected bundle is absent.
    """
    if not frozen or not platform.startswith("linux"):
        return None

    bundle_dir = resource_dir / INJECTED_BUNDLE_DIRNAME
    bundle_library = bundle_dir / _INJECTED_BUNDLE_FILENAME
    if not bundle_library.is_file():
        raise RuntimeError(
            "Frozen Linux application is missing the matching WebKitGTK injected "
            f"bundle {_INJECTED_BUNDLE_FILENAME!r} at {bundle_library}"
        )

    environ[INJECTED_BUNDLE_ENV] = str(bundle_dir)
    return bundle_dir
