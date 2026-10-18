"""
Startup cleanup tests.

Every launch performs a best-effort sweep of leftover PreviewGen temp
directories. It must reclaim directories abandoned by crashed instances while
never clobbering the live temp directory of another running instance.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.tempfiles import (
    OWNER_MARKER,
    STALE_AGE_SECONDS,
    _pid_alive,
    cleanup_stale_temp_dirs,
    create_temp_dir,
)

pytestmark = pytest.mark.core


def _make_marked(base: Path, prefix: str, pid: int, created: float | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
    # Default created timestamp is older than MINIMUM_DELETION_AGE_SECONDS (e.g. 120s ago)
    default_created = time.time() - 120.0
    ts = created if created is not None else default_created
    (d / OWNER_MARKER).write_text(
        json.dumps({
            "instanceId": "test_inst_123",
            "pid": pid,
            "created": ts,
            "kind": prefix.strip("_"),
            "user": "test",
        }),
        encoding="utf-8",
    )
    os.utime(d, (ts, ts))
    return d


def _dead_pid() -> int:
    for candidate in range(2_100_000_000, 2_147_483_000):
        if not _pid_alive(candidate):
            return candidate
    raise RuntimeError("could not find an unused pid")


def test_second_instance_keeps_first_instances_active_temp(tmp_path):
    # Instance A (this process) owns a live, freshly created temp directory.
    active = create_temp_dir("previewgen_scan_", base_dir=tmp_path)
    # Instance B previously crashed and left a fresh directory owned by a dead pid.
    abandoned = _make_marked(tmp_path, "previewgen_render_", pid=_dead_pid())

    removed = cleanup_stale_temp_dirs(base=tmp_path)

    assert active.is_dir(), "a live instance's temp dir must survive another instance's cleanup"
    assert not abandoned.exists()
    assert removed == 1


def test_dead_owner_dir_is_removed_even_when_recent(tmp_path):
    d = _make_marked(tmp_path, "previewgen_ondemand_", pid=_dead_pid())
    removed = cleanup_stale_temp_dirs(base=tmp_path)
    assert removed == 1
    assert not d.exists()


def test_live_owner_dir_is_retained(tmp_path):
    d = _make_marked(tmp_path, "previewgen_preview_", pid=os.getpid())
    removed = cleanup_stale_temp_dirs(base=tmp_path)
    assert removed == 0
    assert d.is_dir()


def test_old_unmarked_dir_is_removed_fresh_unmarked_is_kept(tmp_path):
    old = Path(tempfile.mkdtemp(prefix="previewgen_batch_zip_", dir=str(tmp_path)))
    fresh = Path(tempfile.mkdtemp(prefix="previewgen_sync_scan_", dir=str(tmp_path)))
    past = time.time() - STALE_AGE_SECONDS - 120
    os.utime(old, (past, past))

    removed = cleanup_stale_temp_dirs(base=tmp_path)

    assert removed == 1
    assert not old.exists()
    assert fresh.is_dir(), "a fresh directory without a marker may belong to a live legacy instance"


def test_unrelated_directory_is_never_removed(tmp_path):
    unrelated = Path(tempfile.mkdtemp(prefix="some_other_tool_", dir=str(tmp_path)))
    past = time.time() - STALE_AGE_SECONDS - 120
    os.utime(unrelated, (past, past))

    removed = cleanup_stale_temp_dirs(base=tmp_path)

    assert removed == 0
    assert unrelated.is_dir()
