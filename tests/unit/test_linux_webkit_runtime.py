"""Linux WebKitGTK runtime configuration for frozen applications."""

from __future__ import annotations

from pathlib import Path

import pytest

from previewgen.linux_webkit import (
    INJECTED_BUNDLE_DIRNAME,
    INJECTED_BUNDLE_ENV,
    configure_linux_webkit_runtime,
)

pytestmark = pytest.mark.core


def test_frozen_linux_uses_bundled_webkit_injected_bundle(tmp_path: Path) -> None:
    resource_dir = tmp_path / "resources"
    bundle_dir = resource_dir / INJECTED_BUNDLE_DIRNAME
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "libwebkit2gtkinjectedbundle.so").write_bytes(b"matching bundle")
    environ: dict[str, str] = {}

    configured = configure_linux_webkit_runtime(
        resource_dir,
        platform="linux",
        environ=environ,
        frozen=True,
    )

    assert configured == bundle_dir
    assert environ[INJECTED_BUNDLE_ENV] == str(bundle_dir)


def test_frozen_linux_fails_when_matching_injected_bundle_is_missing(tmp_path: Path) -> None:
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    environ: dict[str, str] = {}

    with pytest.raises(RuntimeError, match="libwebkit2gtkinjectedbundle"):
        configure_linux_webkit_runtime(
            resource_dir,
            platform="linux",
            environ=environ,
            frozen=True,
        )

    assert INJECTED_BUNDLE_ENV not in environ


def test_source_checkout_leaves_host_webkit_configuration_untouched(tmp_path: Path) -> None:
    environ = {INJECTED_BUNDLE_ENV: "/usr/lib/host/libwebkit2gtkinjectedbundle.so"}

    configured = configure_linux_webkit_runtime(
        tmp_path,
        platform="linux",
        environ=environ,
        frozen=False,
    )

    assert configured is None
    assert environ == {INJECTED_BUNDLE_ENV: "/usr/lib/host/libwebkit2gtkinjectedbundle.so"}
