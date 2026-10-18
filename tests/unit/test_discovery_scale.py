"""
Scale and hazard tests for bounded, cancellable batch discovery.

These exercise the failure modes that a naive ``rglob`` traversal cannot
survive: enormous sibling counts, permission-heavy trees, an output directory
nested inside the input, and a network share that stalls past the deadline.
"""
import os
import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch import discovery as discovery_module
from previewgen.batch.discovery import DiscoveryLimits, DiscoveryStats, discover_files
from processor import PreviewConfig, process_folder

pytestmark = pytest.mark.core


def _discover(root: Path, **overrides) -> tuple[list[Path], DiscoveryStats]:
    stats = DiscoveryStats()
    options = dict(
        is_cancelled=lambda: False,
        excluded_roots=set(),
        limits=DiscoveryLimits(),
        supported_extensions=(".png", ".jpg"),
        stats=stats,
    )
    options.update(overrides)
    found = list(discover_files(root, **options))
    return found, stats


def test_discovery_handles_hundred_thousand_plus_files(tmp_path, monkeypatch):
    """Discovery must stream 100,000+ entries and stop at the file cap."""
    root = tmp_path / "huge"
    root.mkdir()

    def fake_walk(dirpath, topdown=True, onerror=None, followlinks=False):
        names = [f"asset-{i:06d}.png" for i in range(100_050)]
        yield (str(dirpath), [], names)

    monkeypatch.setattr(discovery_module.os, "walk", fake_walk)

    found, stats = _discover(root)

    assert len(found) == 100_000
    assert stats.files == 100_000
    assert stats.truncated is True
    assert stats.reasons == ["maximum_files"]


def test_discovery_over_real_filesystem_many_files(tmp_path):
    root = tmp_path / "batch"
    root.mkdir()
    for i in range(1_200):
        (root / f"frame-{i:05d}.png").write_bytes(b"")

    found, stats = _discover(root)

    assert len(found) == 1_200
    assert stats.files == 1_200
    assert stats.truncated is False
    assert stats.reasons == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission semantics")
def test_permission_heavy_tree_reports_inaccessible_directories(tmp_path):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses filesystem permission checks")

    root = tmp_path / "root"
    (root / "open").mkdir(parents=True)
    (root / "locked").mkdir()
    (root / "open" / "visible.png").write_bytes(b"")
    (root / "locked" / "hidden.png").write_bytes(b"")

    os.chmod(root / "locked", 0o000)
    try:
        found, stats = _discover(root)
    finally:
        os.chmod(root / "locked", 0o755)

    assert root / "open" / "visible.png" in found
    assert stats.permission_errors > 0
    assert stats.inaccessible_directories
    assert stats.truncated is True
    assert "permission_denied" in stats.reasons


def test_output_directory_nested_inside_input_is_excluded(tmp_path):
    in_dir = tmp_path / "input"
    (in_dir / "nested").mkdir(parents=True)
    out_dir = in_dir / "out"
    out_dir.mkdir()

    Image.new("RGB", (32, 32), (10, 20, 30)).save(in_dir / "nested" / "photo.png")
    # A stale rendered artifact living inside the (nested) output directory.
    (out_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    summary = process_folder(
        in_dir,
        out_dir,
        PreviewConfig(),
        progress=lambda *_a: None,
        is_cancelled=lambda: False,
    )

    # Only the real source is planned; the nested output artifact is skipped.
    assert summary["planned"] == 1, summary
    assert summary["success"] == 1, summary


def test_network_share_deadline_truncates_discovery(tmp_path, monkeypatch):
    root = tmp_path / "share"
    sub = root / "deep"
    sub.mkdir(parents=True)

    def fake_walk(dirpath, topdown=True, onerror=None, followlinks=False):
        yield (str(root), ["deep"], ["a.png"])
        yield (str(sub), [], ["b.png"])

    monkeypatch.setattr(discovery_module.os, "walk", fake_walk)

    # The first two monotonic() calls are the baseline + first directory; every
    # later call jumps far past the deadline, simulating a stalled network share.
    calls = {"n": 0}

    def fake_monotonic() -> float:
        calls["n"] += 1
        return 0.0 if calls["n"] <= 2 else 10_000.0

    monkeypatch.setattr(discovery_module.time, "monotonic", fake_monotonic)

    found, stats = _discover(root, limits=DiscoveryLimits(timeout_seconds=5.0))

    assert len(found) == 1
    assert stats.truncated is True
    assert "maximum_time" in stats.reasons
