import pytest

"""
Render hygiene: a completed render must not leave temporary directories or
orphaned child processes behind, in either the in-process or the isolated
renderer path.
"""
import multiprocessing
import tempfile
from pathlib import Path

from previewgen.renderer_process import render_file_with_timeout
from processor import PreviewConfig, generate_file

pytestmark = pytest.mark.core

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _previewgen_temp_entries() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob("previewgen_*")}


def test_in_process_render_leaves_no_temp_files_or_child_processes():
    before = _previewgen_temp_entries()

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "hygiene.jpg"
        generate_file(FIXTURES / "sample.png", out, PreviewConfig())
        assert out.is_file() and out.stat().st_size > 0
    leaked = _previewgen_temp_entries() - before
    assert not leaked, f"in-process render leaked temp directories: {sorted(leaked)}"
    assert multiprocessing.active_children() == [], "in-process render left child processes running"


def test_isolated_render_leaves_no_temp_files_or_child_processes():
    before = _previewgen_temp_entries()

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "isolated.jpg"
        render_file_with_timeout(
            FIXTURES / "sample.png",
            out,
            PreviewConfig(),
            timeout_seconds=60.0,
            is_cancelled=lambda: False,
        )
        assert out.is_file() and out.stat().st_size > 0

    leaked = _previewgen_temp_entries() - before
    assert not leaked, f"isolated render leaked temp directories: {sorted(leaked)}"
    assert multiprocessing.active_children() == [], "isolated render left child processes running"
