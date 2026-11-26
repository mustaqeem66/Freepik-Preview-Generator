"""PyInstaller hook coverage for the matching WebKitGTK injected bundle."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from PyInstaller.utils.hooks import gi

from previewgen.linux_webkit import INJECTED_BUNDLE_DIRNAME

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = PROJECT_ROOT / "hooks" / "hook-gi.repository.WebKit2.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("previewgen_webkit_hook", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_freezes_injected_bundle_from_selected_webkit_library_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    library_dir = tmp_path / "usr" / "lib" / "x86_64-linux-gnu"
    library_dir.mkdir(parents=True)
    webkit_library = library_dir / "libwebkit2gtk-4.1.so.0"
    webkit_library.write_bytes(b"webkit library")
    injected_bundle = library_dir / "webkit2gtk-4.1" / "injected-bundle" / "libwebkit2gtkinjectedbundle.so"
    injected_bundle.parent.mkdir(parents=True)
    injected_bundle.write_bytes(b"matching injected bundle")
    typelib = tmp_path / "WebKit2-4.1.typelib"
    typelib.write_bytes(b"typelib")

    class FakeGiModuleInfo:
        def __init__(self, module: str, version: str) -> None:
            assert (module, version) == ("WebKit2", "4.1")
            self.available = True

        def collect_typelib_data(self):
            return [(str(webkit_library), ".")], [(str(typelib), "gi_typelibs")], []

        def get_libdir(self) -> str:
            return str(library_dir)

    monkeypatch.setattr(gi, "GiModuleInfo", FakeGiModuleInfo)

    hook = _load_hook()

    assert (str(injected_bundle), INJECTED_BUNDLE_DIRNAME) in hook.datas
