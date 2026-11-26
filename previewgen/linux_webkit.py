"""Linux WebKitGTK runtime configuration.

A frozen PreviewGen application must use the WebKitGTK injected bundle that
matches its frozen WebKitGTK shared library. Source checkouts continue to use
the host's matching WebKitGTK installation.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path

INJECTED_BUNDLE_ENV = "WEBKIT_INJECTED_BUNDLE_PATH"
INJECTED_BUNDLE_DIRNAME = "webkit_injected_bundle"
_INJECTED_BUNDLE_FILENAME = "libwebkit2gtkinjectedbundle.so"


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
