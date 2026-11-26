"""PyInstaller hook coverage for the matching WebKitGTK injected bundle."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from PyInstaller.utils.hooks import gi

from previewgen import linux_webkit

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = PROJECT_ROOT / "hooks" / "hook-gi.repository.WebKit2.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("previewgen_webkit_hook", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_gi_module_info(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str,
    library_dir: Path,
    webkit_library: Path,
    typelib: Path,
) -> None:
    class FakeGiModuleInfo:
        def __init__(self, module: str, selected_version: str) -> None:
            assert module == "WebKit2"
            self.available = selected_version == version

        def collect_typelib_data(self):
            return [(str(webkit_library), ".")], [(str(typelib), "gi_typelibs")], []

        def get_libdir(self) -> str:
            return str(library_dir)

    monkeypatch.setattr(gi, "GiModuleInfo", FakeGiModuleInfo)


@pytest.mark.parametrize(
    ("version", "bundle_relative_path"),
    [
        ("4.1", "webkit2gtk-4.1/injected-bundle/libwebkit2gtkinjectedbundle.so"),
        ("4.0", "webkit2gtk-4.0/injected-bundle/libwebkit2gtkinjectedbundle.so"),
        ("4.1", "libwebkit2gtkinjectedbundle.so"),
    ],
    ids=["versioned-4.1", "versioned-4.0", "direct-fallback"],
)
def test_hook_freezes_matching_bundle_and_provenance_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    version: str,
    bundle_relative_path: str,
) -> None:
    library_dir = tmp_path / "usr" / "lib" / "x86_64-linux-gnu"
    library_dir.mkdir(parents=True)
    webkit_library = library_dir / f"libwebkit2gtk-{version}.so.0"
    webkit_library.write_bytes(b"selected webkit library")
    injected_bundle = library_dir / bundle_relative_path
    injected_bundle.parent.mkdir(parents=True, exist_ok=True)
    injected_bundle.write_bytes(b"matching injected bundle")
    typelib = tmp_path / f"WebKit2-{version}.typelib"
    typelib.write_bytes(b"typelib")

    _fake_gi_module_info(
        monkeypatch,
        version=version,
        library_dir=library_dir,
        webkit_library=webkit_library,
        typelib=typelib,
    )
    monkeypatch.setattr(
        linux_webkit,
        "read_elf_needed_libraries",
        lambda path: [f"libwebkit2gtk-{version}.so.0", f"libjavascriptcoregtk-{version}.so.0"],
    )
    monkeypatch.setattr(linux_webkit, "read_dpkg_package_version", lambda package: "1:2.50.4-1")

    hook = _load_hook()

    assert (str(injected_bundle), linux_webkit.INJECTED_BUNDLE_DIRNAME) in hook.datas
    manifest_entry = next(
        entry
        for entry in hook.datas
        if entry[1] == linux_webkit.INJECTED_BUNDLE_DIRNAME and entry[0].endswith(linux_webkit.WEBKIT_MANIFEST_FILENAME)
    )
    manifest = json.loads(Path(manifest_entry[0]).read_text(encoding="utf-8"))
    assert manifest["api_version"] == version
    assert manifest["package_name"] == f"libwebkit2gtk-{version}-0"
    assert manifest["package_version"] == "1:2.50.4-1"
    assert manifest["library_filename"] == webkit_library.name
    assert manifest["library_sha256"] == hashlib.sha256(webkit_library.read_bytes()).hexdigest()
    assert manifest["injected_bundle_filename"] == injected_bundle.name
    assert manifest["injected_bundle_sha256"] == hashlib.sha256(injected_bundle.read_bytes()).hexdigest()
    assert manifest["injected_bundle_needed"] == [
        f"libwebkit2gtk-{version}.so.0",
        f"libjavascriptcoregtk-{version}.so.0",
    ]


def test_hook_fails_closed_when_selected_webkit_has_no_injected_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    library_dir = tmp_path / "usr" / "lib" / "x86_64-linux-gnu"
    library_dir.mkdir(parents=True)
    webkit_library = library_dir / "libwebkit2gtk-4.1.so.0"
    webkit_library.write_bytes(b"selected webkit library")
    typelib = tmp_path / "WebKit2-4.1.typelib"
    typelib.write_bytes(b"typelib")
    _fake_gi_module_info(
        monkeypatch,
        version="4.1",
        library_dir=library_dir,
        webkit_library=webkit_library,
        typelib=typelib,
    )

    with pytest.raises(RuntimeError, match="injected bundle not found"):
        _load_hook()
