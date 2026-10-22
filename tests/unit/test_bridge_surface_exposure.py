"""The pywebview bridge must expose a flat, reviewed list of operations.

``webview.util.get_functions`` walks ``dir(js_api)`` recursively and publishes
every attribute that does not start with ``_`` and is not marked
``_serializable = False``. Anything it finds becomes callable from the page,
which is how a rendered document could otherwise mint its own source-read
grant or drive the native window handle.
"""
from __future__ import annotations

import inspect

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
    """Replicate webview.util.get_functions over the live api object."""
    names: set[str] = set()
    visited: list[int] = []

    def walk(obj: object, base: str = "") -> None:
        if id(obj) in visited:
            return
        visited.append(id(obj))
        for attr_name in dir(obj):
            full = f"{base}.{attr_name}" if base else attr_name
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(obj, attr_name)
            except Exception:  # noqa: BLE001 - mirrors pywebview's own guard
                continue
            if not getattr(attr, "_serializable", True):
                continue
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                names.add(full)
            elif inspect.isclass(attr) or (
                isinstance(attr, object) and not callable(attr)
                and hasattr(attr, "__module__")
            ):
                walk(attr, full)

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
