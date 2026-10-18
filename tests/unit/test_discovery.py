"""Bounded, cancellable batch discovery."""
import os
import sys
from pathlib import Path

import pytest

from previewgen.batch.discovery import DiscoveryLimits, DiscoveryStats, discover_files

pytestmark = pytest.mark.core

SUPPORTED = (".png", ".jpg", ".svg")


def _discover(root: Path, *, is_cancelled=None, excluded_roots=None, **limit_overrides):
    stats = DiscoveryStats()
    defaults = {"maximum_files": 1000, "maximum_directories": 1000,
                "timeout_seconds": 60.0, "max_depth": 15}
    limits = DiscoveryLimits(**{**defaults, **limit_overrides})
    files = list(
        discover_files(
            root,
            is_cancelled=is_cancelled or (lambda: False),
            excluded_roots=excluded_roots or set(),
            limits=limits,
            supported_extensions=SUPPORTED,
            stats=stats,
        )
    )
    return files, stats


def test_discover_yields_supported_files_in_deterministic_order(tmp_path):
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.jpg").write_bytes(b"x")

    files, stats = _discover(tmp_path)

    assert files == [tmp_path / "a.png", tmp_path / "b.png", sub / "c.jpg"]
    assert stats.files == 3
    assert not stats.cancelled and not stats.truncated


def test_discovery_stops_promptly_when_cancelled(tmp_path):
    for i in range(40):
        (tmp_path / f"file{i:03d}.png").write_bytes(b"x")

    stats = DiscoveryStats()
    seen: list[Path] = []

    def is_cancelled() -> bool:
        return len(seen) >= 3

    for path in discover_files(
        tmp_path,
        is_cancelled=is_cancelled,
        excluded_roots=set(),
        limits=DiscoveryLimits(maximum_files=1000, maximum_directories=1000, timeout_seconds=60.0),
        supported_extensions=SUPPORTED,
        stats=stats,
    ):
        seen.append(path)

    assert len(seen) == 3, "traversal did not stop immediately on cancellation"
    assert stats.cancelled is True
    assert stats.files == 3


def test_discovery_excludes_nested_output_root(tmp_path):
    (tmp_path / "keep.png").write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    (out / "generated.png").write_bytes(b"x")
    (out / "nested").mkdir()
    (out / "nested" / "deep.png").write_bytes(b"x")

    files, _ = _discover(tmp_path, excluded_roots={out})

    assert files == [tmp_path / "keep.png"]


def test_discovery_enforces_file_cap(tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.png").write_bytes(b"x")

    files, stats = _discover(tmp_path, maximum_files=2)

    assert len(files) == 2
    assert stats.truncated is True
    assert "maximum_files" in stats.reasons


def test_discovery_enforces_depth_limit(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "deep.png").write_bytes(b"x")
    (tmp_path / "top.png").write_bytes(b"x")

    files, stats = _discover(tmp_path, max_depth=1)

    assert files == [tmp_path / "top.png"]
    assert stats.truncated is True
    assert "maximum_depth" in stats.reasons


@pytest.mark.skipif(sys.platform == "win32", reason="symlink semantics differ on Windows")
def test_discovery_does_not_follow_symlinked_directories(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "inside.png").write_bytes(b"x")
    link = tmp_path / "link"
    os.symlink(real, link, target_is_directory=True)
    loop = real / "loop"
    os.symlink(tmp_path, loop, target_is_directory=True)

    files, stats = _discover(tmp_path)

    assert real / "inside.png" in files
    # The symlinked directory itself is never traversed (no duplicate/loop hits).
    assert link / "inside.png" not in files
    assert stats.skipped >= 1


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="permission errors are unenforceable on Windows or as root",
)
def test_discovery_handles_permission_errors_without_aborting(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "hidden.png").write_bytes(b"x")
    (tmp_path / "visible.png").write_bytes(b"x")
    os.chmod(locked, 0o000)
    try:
        files, stats = _discover(tmp_path)
    finally:
        os.chmod(locked, 0o755)

    assert tmp_path / "visible.png" in files
    assert stats.permission_errors >= 1
@pytest.mark.skipif(sys.platform == "win32", reason="symlink semantics differ on Windows")
def test_discovery_file_symlink_policy(tmp_path):
    """Allow file symlinks whose target is within root; reject external target escapes."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    real_inside = root / "real_inside.png"
    real_inside.write_bytes(b"inside")
    real_outside = outside / "secret.png"
    real_outside.write_bytes(b"outside")

    # 1. Symlink pointing to an asset inside root (allowed)
    valid_link = root / "link_inside.png"
    valid_link.symlink_to(real_inside)

    # 2. Symlink pointing outside root (must be rejected/escaped)
    escape_link = root / "escape_outside.png"
    escape_link.symlink_to(real_outside)

    # 3. Broken symlink (must be rejected)
    broken_link = root / "broken.png"
    broken_link.symlink_to(root / "nonexistent.png")

    files, stats = _discover(root)
    assert real_inside in files
    assert valid_link in files
    assert escape_link not in files
    assert broken_link not in files
    assert stats.skipped >= 2
