"""Bundle the WebKit2 GObject-introspection typelib that pywebview's GTK backend needs.

PyInstaller ships hooks for many ``gi.repository`` namespaces but not for WebKit2, so a
frozen Linux app can import ``gi`` yet fail to resolve ``WebKit2`` at runtime and fall
back to its headless smoke path.
"""
from PyInstaller.utils.hooks.gi import GiModuleInfo

binaries = []
datas = []
hiddenimports = []

# pywebview prefers the 4.1 API stack and drops to 4.0 when it is absent; bundle
# whichever one this build host actually provides.
for version in ("4.1", "4.0"):
    module_info = GiModuleInfo("WebKit2", version)
    if module_info.available:
        binaries, datas, hiddenimports = module_info.collect_typelib_data()
        break
