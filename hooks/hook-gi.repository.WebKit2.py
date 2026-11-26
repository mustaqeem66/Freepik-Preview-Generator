"""Bundle the WebKit2 GObject-introspection typelib that pywebview's GTK backend needs.

PyInstaller ships hooks for many ``gi.repository`` namespaces but not for WebKit2, so a
frozen Linux app can import ``gi`` yet fail to resolve ``WebKit2`` at runtime and fall
back to its headless smoke path.
"""

from pathlib import Path

from PyInstaller.utils.hooks.gi import GiModuleInfo

from previewgen.linux_webkit import INJECTED_BUNDLE_DIRNAME

binaries = []
datas = []
hiddenimports = []

# pywebview prefers the 4.1 API stack and drops to 4.0 when it is absent; bundle
# whichever one this build host actually provides.
for version in ("4.1", "4.0"):
    module_info = GiModuleInfo("WebKit2", version)
    if module_info.available:
        binaries, datas, hiddenimports = module_info.collect_typelib_data()

        # WebKit's child process loads this bundle separately from the frozen
        # WebKitGTK library. Freeze the copy beside that library so both use one
        # ABI, even when the runtime host has a newer WebKitGTK package.
        library_dir = module_info.get_libdir()
        if library_dir is None:
            raise RuntimeError(f"WebKitGTK {version} does not resolve to a shared-library directory")
        library_path = Path(library_dir)
        injected_bundle_candidates = (
            library_path / f"webkit2gtk-{version}" / "injected-bundle" / "libwebkit2gtkinjectedbundle.so",
            library_path / "libwebkit2gtkinjectedbundle.so",
        )
        injected_bundle = next((path for path in injected_bundle_candidates if path.is_file()), None)
        if injected_bundle is None:
            candidates = ", ".join(str(path) for path in injected_bundle_candidates)
            raise RuntimeError(f"WebKitGTK {version} injected bundle not found; checked: {candidates}")
        datas.append((str(injected_bundle), INJECTED_BUNDLE_DIRNAME))
        break
