"""ZIP mesh preview cache identity regressions."""
from __future__ import annotations

import shutil
import zipfile

import pytest

pytestmark = pytest.mark.core


def test_member_key_separates_distinct_archive_entries_and_updates(tmp_path):
    from previewgen.renderers.mesh3d import _archive_mesh_cache_key
    archive = tmp_path / "assets.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("one.obj", "v 0 0 0\n")
        zf.writestr("two.obj", "v 1 0 0\n")
    with zipfile.ZipFile(archive) as zf:
        first = _archive_mesh_cache_key(archive, zf.getinfo("one.obj"))
        second = _archive_mesh_cache_key(archive, zf.getinfo("two.obj"))
    assert first != second
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("one.obj", "v 2 0 0\n")
    with zipfile.ZipFile(archive) as zf:
        updated = _archive_mesh_cache_key(archive, zf.getinfo("one.obj"))
    assert updated != first


def test_3d_mesh_cache_reuses_extracted_archive_content(monkeypatch, tmp_path):
    trimesh = pytest.importorskip("trimesh")
    from previewgen.config import PreviewConfig
    from previewgen.renderers import mesh3d

    source = tmp_path / "original.obj"
    source.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    extracted1 = tmp_path / "job-one" / "original.obj"
    extracted2 = tmp_path / "job-two" / "original.obj"
    extracted1.parent.mkdir()
    extracted2.parent.mkdir()
    shutil.copy2(source, extracted1)
    shutil.copy2(source, extracted2)

    loads = []
    original = trimesh.load
    def spy(path, *args, **kwargs):
        loads.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(trimesh, "load", spy)
    mesh3d._MESH_CACHE.clear()
    token = mesh3d._ARCHIVE_SOURCE_CACHE_KEY.set(("zip://archive.zip?entry=original.obj", 1, 1, 100))
    try:
        mesh3d._load_3d(extracted1, PreviewConfig(), 64)
        mesh3d._load_3d(extracted2, PreviewConfig(), 64)
    finally:
        mesh3d._ARCHIVE_SOURCE_CACHE_KEY.reset(token)
        mesh3d._MESH_CACHE.clear()
    assert len(loads) == 1
