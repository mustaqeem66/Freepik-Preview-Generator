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
        injected_bundle = Path(library_dir) / "libwebkit2gtkinjectedbundle.so"
        if not injected_bundle.is_file():
            raise RuntimeError(
                f"WebKitGTK {version} injected bundle not found beside the selected library: {injected_bundle}"
            )
        datas.append((str(injected_bundle), INJECTED_BUNDLE_DIRNAME))
        break
