"""End-to-end native picker -> capability grant on Linux.

#21 and #59 both hinge on one claim: a capability is granted only when the
user chooses it in the *operating-system* file dialog. Unit tests simulate the
grant; this drives the real GTK chooser pywebview opens and asserts what the
application may read afterwards.

The GUI session runs in a subprocess on purpose. ``webview.start()`` owns the
thread that runs it, so a test that started it in-process would leave pytest's
own process multi-threaded, and the batch tests that fork a renderer afterwards
then deadlock inside ``multiprocessing``. Only one asset is picked per dialog:
a headless ``GtkFileChooser`` replaces rather than extends its selection when
``select_filename()`` is applied twice, so multi-select stays covered by the
unit-level grant tests instead of being faked here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.full_runtime,
    pytest.mark.skipif(sys.platform != "linux", reason="GTK chooser is the Linux native path"),
    pytest.mark.skipif(
        not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        reason="native file dialogs need a display",
    ),
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHILD_FLAG = "--native-picker-child"
BUDGET = 600  # ticks at 80ms; the 90s session watchdog is the real stop
EVIDENCE_PREFIX = "PICKER_EVIDENCE "


def _observe_session(workdir: Path) -> dict[str, object]:
    """Run the real picker flow and report the permissions it left behind."""
    sys.path.insert(0, str(PROJECT_ROOT))
    import threading

    import webview
    from gi.repository import Gdk, GLib, Gtk
    from PIL import Image

    from previewgen.api import DesktopApi

    chosen = workdir / "chosen.png"
    Image.new("RGB", (24, 24), "red").save(chosen)
    Image.new("RGB", (24, 24), "blue").save(workdir / "sibling.png")
    Image.new("RGB", (24, 24), "green").save(workdir / "never-picked.png")
    (workdir / "notes.txt").write_text("not artwork", encoding="utf-8")

    api = DesktopApi()
    evidence: dict[str, object] = {}
    finished = threading.Event()
    state = {"ticks": 0, "navigated": set(), "answered": [], "pick": chosen}

    def ready(dialog) -> bool:
        key = id(dialog)
        if key not in state["navigated"]:
            dialog.set_current_folder(str(workdir))
            state["navigated"].add(key)
        dialog.select_filename(str(state["pick"]))
        return Path(dialog.get_filename() or "") == state["pick"]

    def poll() -> bool:
        state["ticks"] += 1
        give_up = state["ticks"] >= BUDGET
        evidence["give_up"] = give_up
        for toplevel in Gtk.Window.list_toplevels():
            if not isinstance(toplevel, Gtk.FileChooserDialog):
                continue
            key = id(toplevel)
            if key in state["answered"]:
                continue
            if not ready(toplevel) and not give_up:
                return True
            state["answered"].append(key)
            toplevel.response(Gtk.ResponseType.CANCEL if give_up else Gtk.ResponseType.OK)
            return False
        return True

    def ask(driver_pick: Path, call):
        state["pick"] = driver_pick
        Gdk.threads_add_timeout(GLib.PRIORITY_DEFAULT, 80, poll)
        return call()

    def scenario() -> None:
        try:
            evidence["files"] = ask(chosen, api.browse_files)
            # Snapshot before the folder dialog widens the read capability.
            evidence["exact"] = api._is_authorized_selected_file(chosen)
            evidence["sibling"] = api._is_authorized_selected_file(workdir / "sibling.png")
            evidence["folder_read"] = api._is_authorized_input_path(workdir / "sibling.png")
            evidence["folder"] = ask(workdir, api.browse_input_folder)
            evidence["granted_read"] = api._is_authorized_input_path(workdir / "never-picked.png")
            evidence["write_granted"] = api._is_authorized_output_path(workdir)
            evidence["preview"] = api.start_preview(str(workdir / "never-picked.png"), {})
            outside = workdir.parent / "picker-outside.png"
            Image.new("RGB", (24, 24), "white").save(outside)
            evidence["outside"] = api.start_preview(str(outside), {})
            evidence["non_image"] = api._source_read_error(str(workdir / "notes.txt"))
            Path(outside).unlink(missing_ok=True)
        finally:
            finished.set()
            # destroy() marshals back to the GUI loop; joining it here would
            # block that same loop, because webview.start runs launch() on it.
            window.destroy()

    def launch() -> None:
        threading.Thread(target=scenario, daemon=True).start()

        def watchdog() -> bool:
            if not finished.is_set():
                evidence["error"] = "native dialog was never answered"
                window.destroy()
            return False

        GLib.timeout_add_seconds(90, watchdog)

    window = webview.create_window("picker-e2e", url="about:blank", js_api=api)
    api._set_window(window)
    webview.start(launch, gui="gtk")
    return evidence


def test_native_picker_selection_is_what_becomes_readable(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), CHILD_FLAG, str(tmp_path)],
        capture_output=True, text=True, timeout=180, cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    line = next(
        (line for line in result.stdout.splitlines() if line.startswith(EVIDENCE_PREFIX)), None
    )
    assert line is not None, f"no evidence line in:\n{result.stdout}\n{result.stderr}"
    evidence = json.loads(line[len(EVIDENCE_PREFIX):])
    assert "error" not in evidence, f"the GUI session stalled: {evidence}"
    assert evidence["give_up"] is False, f"the native dialog was never answered: {evidence}"

    files = evidence["files"]
    assert files["ok"] is True, files
    assert [Path(entry["path"]).name for entry in files["value"]["files"]] == ["chosen.png"]
    assert files["value"]["rejected"] == []

    # Add Files grants the picked asset alone -- not its sibling, not its folder.
    assert evidence["exact"] is True
    assert evidence["sibling"] is False
    assert evidence["folder_read"] is False

    # Choose Folder grants the directory for reading, and nothing for writing.
    assert Path(str(evidence["folder"])).resolve() == tmp_path.resolve()
    assert evidence["granted_read"] is True
    assert evidence["write_granted"] is False

    assert evidence["preview"]["ok"] is True
    assert evidence["outside"]["error"] == "UNAUTHORIZED_SOURCE"
    assert evidence["non_image"] == "UNSUPPORTED_SOURCE"


if __name__ == "__main__" and CHILD_FLAG in sys.argv:
    print(EVIDENCE_PREFIX + json.dumps(_observe_session(Path(sys.argv[-1]))))
    raise SystemExit(0)
