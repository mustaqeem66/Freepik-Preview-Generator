"""
Render hygiene: a completed render must not leave temporary directories or
orphaned child processes behind, in either the in-process or the isolated
renderer path.
"""
import multiprocessing
import tempfile
from pathlib import Path

import pytest

from previewgen.renderer_process import render_file_with_timeout
from processor import PreviewConfig, generate_file

pytestmark = pytest.mark.core

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def temp_root(tmp_path: Path, monkeypatch) -> Path:
    """Redirect the system temp folder into a directory owned by this test.

    Assigning ``tempfile.tempdir`` covers in-process renders and forked
    children, and the matching environment variables are inherited by
    children started with spawn. Without this the check reads the real
    ``/tmp``, where any concurrent PreviewGen run looks like a leak.
    """
    root = tmp_path / "system-tmp"
    root.mkdir()
    for var in ("TMPDIR", "TMP", "TEMP"):
        monkeypatch.setenv(var, str(root))
    monkeypatch.setattr(tempfile, "tempdir", str(root), raising=False)
    return root


def _previewgen_temp_entries(root: Path) -> set[str]:
    return {p.name for p in root.glob("previewgen_*")}


def test_in_process_render_leaves_no_temp_files_or_child_processes(temp_root: Path):
    before = _previewgen_temp_entries(temp_root)

    out = temp_root / "hygiene.jpg"
    generate_file(FIXTURES / "sample.png", out, PreviewConfig())
    assert out.is_file() and out.stat().st_size > 0

    leaked = _previewgen_temp_entries(temp_root) - before
    assert not leaked, f"in-process render leaked temp directories: {sorted(leaked)}"
    assert multiprocessing.active_children() == [], "in-process render left child processes running"


def test_isolated_render_leaves_no_temp_files_or_child_processes(temp_root: Path):
    before = _previewgen_temp_entries(temp_root)

    out = temp_root / "isolated.jpg"
    render_file_with_timeout(
        FIXTURES / "sample.png",
        out,
        PreviewConfig(),
        timeout_seconds=60.0,
        is_cancelled=lambda: False,
    )
    assert out.is_file() and out.stat().st_size > 0

    leaked = _previewgen_temp_entries(temp_root) - before
    assert not leaked, f"isolated render leaked temp directories: {sorted(leaked)}"
    assert multiprocessing.active_children() == [], "isolated render left child processes running"
