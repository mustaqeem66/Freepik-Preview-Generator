"""The pywebview bridge must expose a flat, reviewed list of operations.

``webview.util.get_functions`` walks ``dir(js_api)`` recursively and publishes
every attribute that does not start with ``_`` and is not marked
``_serializable = False``. Anything it finds becomes callable from the page,
which is how a rendered document could otherwise mint its own source-read
grant or drive the native window handle.
"""
from __future__ import annotations

import inspect
import json

import pytest
from PIL import Image

from previewgen.api import DesktopApi

pytestmark = pytest.mark.core

# Every name the page would get, pinned. Adding a method here is a deliberate
# decision about what a document may call; the frontend uses a subset of it.
EXPECTED_BRIDGE = frozenset({
    "browse_files",
    "browse_font",
    "browse_input_folder",
    "browse_logo",
    "browse_output_folder",
    "calculate_export_dimensions",
    "cancel_batch",
    "cancel_preview",
    "cancel_probe",
    "cancel_scan",
    "cleanup",
    "clear_selected_files",
    "export_preview",
    "frontend_ready",
    "get_initial_state",
    "get_scan_page",
    "get_window_chrome",
    "has_outstanding_work",
    "open_diagnostics_folder",
    "open_folder",
    "probe_asset",
    "release_preview",
    "render_preview",
    "request_source_comparison",
    "request_thumbnails",
    "save_settings",
    "scan_folder",
    "start_batch",
    "start_batch_files",
    "start_preview",
    "start_probe",
    "start_scan",
    "window_action",
})

FORBIDDEN = frozenset({
    "add_authorized_folder",
    "add_authorized_input_folder",
    "add_authorized_output_folder",
    "is_authorized_path",
    "is_authorized_input_path",
    "is_authorized_output_path",
    "is_authorized_export_destination",
    "is_authorized_selected_file",
    "set_window",
})


def bridge_visible_names(api: DesktopApi) -> set[str]:
    """Replicate webview.util.get_functions over the live api object.

    The ``try`` covers the whole body, recursion included, exactly as
    ``webview.util.get_functions`` does: upstream logs
    ``Error while processing <path>: maximum recursion depth exceeded`` and
    carries on, which is what a deep toolkit graph turned into on Windows.
    """
    names: set[str] = set()
    visited: list[int] = []

    def walk(obj: object, base: str = "") -> None:
        if id(obj) in visited:
            return
        visited.append(id(obj))
        for attr_name in dir(obj):
            full = f"{base}.{attr_name}" if base else attr_name
            try:
                if attr_name.startswith("_"):
                    continue
                attr = getattr(obj, attr_name)
                if not getattr(attr, "_serializable", True):
                    continue
                if inspect.ismethod(attr) or inspect.isfunction(attr):
                    names.add(full)
                elif inspect.isclass(attr) or (
                    isinstance(attr, object) and not callable(attr)
                    and hasattr(attr, "__module__")
                ):
                    walk(attr, full)
            except RecursionError:
                # Reached a self-renewing graph; record it so the test fails.
                names.add(full)
            except Exception:  # noqa: BLE001 - mirrors pywebview's own guard
                continue

    walk(api)
    return names


@pytest.fixture
def api():
    desktop = DesktopApi()
    try:
        yield desktop
    finally:
        desktop.cleanup()


def test_bridge_surface_is_exactly_the_reviewed_list(api):
    assert bridge_visible_names(api) == set(EXPECTED_BRIDGE)


def test_no_capability_grantor_or_oracle_reaches_the_page(api):
    # A bound native window is the runtime's normal state; binding it must not
    # hand the page the window object itself.
    api._set_window(object())
    visible = bridge_visible_names(api)
    assert not (visible & FORBIDDEN)
    assert not any("." in name for name in visible)


def test_no_grantor_exists_for_a_page_to_call(api, tmp_path):
    source = tmp_path / "not-selected.png"
    Image.new("RGB", (24, 24), "red").save(source)

    for grantor in (
        "add_authorized_folder", "add_authorized_input_folder", "add_authorized_output_folder",
    ):
        assert not hasattr(DesktopApi, grantor), grantor

    denied = api.start_preview(str(source), {})
    assert denied["ok"] is False
    assert denied["error"] == "UNAUTHORIZED_SOURCE"


class _SelfRenewing:
    """Stand-in for a pythonnet-wrapped WinForms/WebView2 object.

    `webview.util.get_functions` memoizes by ``id(obj)``, so a property that
    hands back a *fresh* instance on every access -- which is exactly what
    ``FontFamily.GenericSansSerif`` and the ``SyncRoot`` collections do -- walks
    forever until Python raises `RecursionError`. Reproduced here rather than
    mocked away because it is the mechanism behind the packaged Windows
    "Not Responding" report (issue #19).
    """

    __module__ = "System.Drawing"

    @property
    def GenericSansSerif(self) -> _SelfRenewing:
        return _SelfRenewing()

    @property
    def Families(self) -> _SelfRenewing:
        return _SelfRenewing()

    def Dispose(self) -> None:  # pragma: no cover - only ever enumerated
        pass


class _FakeForm:
    """The public surface of `Window.native` on the Windows backend."""

    __module__ = "System.Windows.Forms"

    ActiveControl = _SelfRenewing()
    DefaultFont = _SelfRenewing()
    ZoomFactor = 1.0

    def Show(self) -> None:  # pragma: no cover - only ever enumerated
        pass


class _FakeWindow:
    """Everything a real `webview.Window` exposes without a leading underscore."""

    def __init__(self) -> None:
        self.native = _FakeForm()
        self.title = "PreviewGen"
        self.gui = "winforms"

    def evaluate_js(self, script: str) -> None:  # pragma: no cover - never called
        pass


def test_binding_a_windows_shaped_window_reaches_no_toolkit_paths(api) -> None:
    api._set_window(_FakeWindow())
    visible = bridge_visible_names(api)
    assert visible == set(EXPECTED_BRIDGE)
    nested = {n for n in visible if "." in n}
    assert not nested, f"page can reach the toolkit graph through {sorted(nested)}"


def test_injected_function_list_stays_small(api) -> None:
    """The function list is serialized into one `run_js` payload.

    A recursive walk of a live backend produced a payload large enough that
    WebView2 rejected the script outright, so the page never finished
    initializing.
    """
    payload = json.dumps([{"func": name, "params": []} for name in bridge_visible_names(api)])
    assert len(payload) < 8192, f"{len(payload)} bytes of bridge surface injected at once"

