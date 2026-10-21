"""Expose ``gi.repository.WebKit2`` as a runtime module so PyGObject hooks can run.

pywebview's GTK backend does ``from gi.repository import WebKit2``, but that name is
resolved by GObject introspection at runtime rather than as an importable file, so
modulegraph records it as a missing module and no hook is attached. PyInstaller ships
this alias for many namespaces (including ``Soup``) but not for WebKit2.
"""


def pre_safe_import_module(api):
    api.add_runtime_module(api.module_name)
