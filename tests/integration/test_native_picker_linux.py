"""End-to-end native picker -> capability grant on Linux.

#21 and #59 both hinge on one claim: a capability is granted only when the
user chooses it in the *operating-system* file dialog. Unit tests simulate the
grant; this drives the real GTK chooser pywebview opens and asserts what the
application may read afterwards.

One ``webview.start`` session runs both scenarios, because the GTK main loop
cannot be re-entered reliably from a second call in the same process. Only one
asset is picked per file dialog: a headless ``GtkFileChooser`` replaces rather
than extends its selection when ``select_filename()`` is applied twice, so
multi-select is left to the unit-level grant tests instead of being faked here.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

import webview  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from previewgen.api import DesktopApi  # noqa: E402

pytestmark = [
    pytest.mark.full_runtime,
    pytest.mark.skipif(sys.platform != "linux", reason="GTK chooser is the Linux native path"),
    pytest.mark.skipif(
        not (GLib.getenv("DISPLAY") or GLib.getenv("WAYLAND_DISPLAY")),
        reason="native file dialogs need a display",
    ),
]


class _ChooserDriver:
    """Answers each native dialog as soon as it holds the wanted selection.

    ``Gtk.Dialog.run()`` nests the default main context, so a timeout source
    added before the call still fires while the chooser is up. The chooser
    loads its folder model asynchronously, so a selection applied on the first
    tick is dropped; the driver re-applies it until the widget reports it back,
    which is the state a real user's click leaves behind.
    """

    budget = 150

    def __init__(self, folder: Path, pick: Path):
        self.folder = folder
        self.pick = pick
        self.ticks = 0
        self.navigated: set[int] = set()
        self.answered: list[int] = []

    def _ready(self, dialog: Gtk.FileChooserDialog, key: int) -> bool:
        if key not in self.navigated:
            dialog.set_current_folder(str(self.folder))
            self.navigated.add(key)
        dialog.select_filename(str(self.pick))
        chosen = dialog.get_filename()
        return chosen is not None and Path(chosen) == self.pick

    def poll(self) -> bool:
        self.ticks += 1
        give_up = self.ticks >= self.budget
        for toplevel in Gtk.Window.list_toplevels():
            if not isinstance(toplevel, Gtk.FileChooserDialog):
                continue
            key = id(toplevel)
            if key in self.answered:
                continue
            if not self._ready(toplevel, key) and not give_up:
                break
            self.answered.append(key)
            toplevel.response(Gtk.ResponseType.CANCEL if give_up else Gtk.ResponseType.OK)
        return self.ticks < self.budget and not self.answered


def test_native_picker_selection_is_what_becomes_readable(tmp_path):
    chosen = tmp_path / "chosen.png"
    Image.new("RGB", (24, 24), "red").save(chosen)
    Image.new("RGB", (24, 24), "blue").save(tmp_path / "sibling.png")
    Image.new("RGB", (24, 24), "green").save(tmp_path / "never-picked.png")
    (tmp_path / "notes.txt").write_text("not artwork", encoding="utf-8")

    api = DesktopApi()
    outcome: dict[str, object] = {}
    finished = threading.Event()

    def _ask(driver: _ChooserDriver, call):
        Gdk.threads_add_timeout(GLib.PRIORITY_DEFAULT, 80, driver.poll)
        return call()

    def scenario() -> None:
        try:
            outcome["files"] = _ask(_ChooserDriver(tmp_path, chosen), api.browse_files)
            # Snapshot before the folder dialog widens the read capability.
            outcome["exact"] = api._is_authorized_selected_file(chosen)
            outcome["sibling"] = api._is_authorized_selected_file(tmp_path / "sibling.png")
            outcome["folder_read"] = api._is_authorized_input_path(tmp_path / "sibling.png")
            outcome["folder"] = _ask(_ChooserDriver(tmp_path, tmp_path),
                                     lambda: api.browse_input_folder())
        finally:
            finished.set()
            # destroy() marshals back to the GUI loop; joining here would block
            # that same loop, because webview.start runs launch() on it.
            api._window.destroy()

    def launch() -> None:
        threading.Thread(target=scenario, daemon=True).start()

        def watchdog() -> bool:
            if not finished.is_set():
                outcome["error"] = "native dialog was never answered"
                api._window.destroy()
            return False

        GLib.timeout_add_seconds(90, watchdog)

    window = webview.create_window("picker-e2e", url="about:blank", js_api=api)
    api._set_window(window)
    webview.start(launch, gui="gtk")

    assert finished.is_set(), "the native GUI session did not finish"
    assert "error" not in outcome, outcome.get("error")

    files = outcome["files"]
    assert files["ok"] is True
    assert [Path(entry["path"]).name for entry in files["value"]["files"]] == ["chosen.png"]
    assert files["value"]["rejected"] == []

    # Add Files grants the picked asset alone -- not its sibling, not the folder.
    assert outcome["exact"] is True
    assert outcome["sibling"] is False
    assert outcome["folder_read"] is False

    # Choose Folder grants the directory for reading, and nothing for writing.
    assert Path(str(outcome["folder"])).resolve() == tmp_path.resolve()
    assert api._is_authorized_input_path(tmp_path / "never-picked.png") is True
    assert api._is_authorized_output_path(tmp_path) is False

    assert api.start_preview(str(tmp_path / "never-picked.png"), {})["ok"] is True
    outside = Path("/tmp/picker-e2e-outside.png")
    Image.new("RGB", (24, 24), "white").save(outside)
    try:
        assert api.start_preview(str(outside), {})["error"] == "UNAUTHORIZED_SOURCE"
    finally:
        outside.unlink(missing_ok=True)
    assert api._source_read_error(str(tmp_path / "notes.txt")) == "UNSUPPORTED_SOURCE"

    api.cleanup()
