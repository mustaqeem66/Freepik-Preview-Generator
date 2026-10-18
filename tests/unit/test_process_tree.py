import contextlib
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import proc
from previewgen.renderer_process import RendererProcessPool

pytestmark = pytest.mark.core

_SPAWN_CHILD_SCRIPT = """
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
with open(sys.argv[1], "w") as fh:
    fh.write(str(child.pid))
time.sleep(60)
"""


def _spawn_stubborn_tree(sandbox: Path) -> tuple[subprocess.Popen, int]:
    script = sandbox / "spawn_child.py"
    script.write_text(_SPAWN_CHILD_SCRIPT)
    pid_file = sandbox / "child.pid"
    if sys.platform == "win32":
        kwargs: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        kwargs = {"start_new_session": True}
    parent = subprocess.Popen([sys.executable, str(script), str(pid_file)], **kwargs)
    deadline = time.time() + 10
    while time.time() < deadline:
        if pid_file.exists() and pid_file.read_text().strip():
            return parent, int(pid_file.read_text().strip())
        time.sleep(0.05)
    parent.kill()
    raise AssertionError("grandchild did not start in time")


def test_is_alive_reports_current_process_and_bogus_pid():
    import os

    assert proc.is_alive(os.getpid()) is True
    assert proc.is_alive(0x7FFFFF00) is False


def test_descendant_pids_tracks_grandchild():
    with tempfile.TemporaryDirectory() as tmp:
        parent, grandchild = _spawn_stubborn_tree(Path(tmp))
        try:
            descendants = proc.descendant_pids(parent.pid)
            assert grandchild in descendants
        finally:
            proc.terminate_process_tree(parent.pid, kill_timeout=3.0)
            with contextlib.suppress(Exception):
                parent.wait(timeout=5)


def test_terminate_process_tree_kills_all_descendants():
    with tempfile.TemporaryDirectory() as tmp:
        parent, grandchild = _spawn_stubborn_tree(Path(tmp))
        try:
            survivors = proc.terminate_process_tree(parent.pid, kill_timeout=5.0)
            assert survivors == set(), f"leaked descendants: {survivors}"
            assert not proc.is_alive(parent.pid)
            assert not proc.is_alive(grandchild)
        finally:
            with contextlib.suppress(Exception):
                parent.wait(timeout=5)


def test_run_with_tree_timeout_kills_spawned_tree():
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        script = sandbox / "spawn_child.py"
        script.write_text(_SPAWN_CHILD_SCRIPT)
        pid_file = sandbox / "child.pid"

        with pytest.raises(TimeoutError):
            proc.run_with_tree_timeout(
                [sys.executable, str(script), str(pid_file)], timeout=3.0
            )

        deadline = time.time() + 5
        while time.time() < deadline and not pid_file.exists():
            time.sleep(0.05)
        assert pid_file.exists()
        grandchild = int(pid_file.read_text().strip())
        deadline = time.time() + 5
        while time.time() < deadline and proc.is_alive(grandchild):
            time.sleep(0.05)
        assert not proc.is_alive(grandchild)


def test_apply_memory_limit_noop_for_non_positive():
    assert proc.apply_memory_limit(0) is False


@pytest.mark.skipif(sys.platform == "win32" or sys.platform == "darwin", reason="RLIMIT_AS is Linux-only")
def test_apply_memory_limit_enforced_in_subprocess():
    script = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from previewgen import proc\n"
        "assert proc.apply_memory_limit(700 * 1024 * 1024)\n"
        "outcome = 'ok'\n"
        "try:\n"
        "    bytearray(2 * 1024 * 1024 * 1024)\n"
        "except MemoryError:\n"
        "    outcome = 'limited'\n"
        "print(outcome)\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "memlimit.py"
        script_path.write_text(script)
        result = subprocess.run(
            [sys.executable, str(script_path), str(PROJECT_ROOT)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "limited"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group specific")
def test_terminate_process_tree_returns_empty_for_dead_pid():
    assert proc.terminate_process_tree(0x7FFFFF00, kill_timeout=0.5) == set()


class _ProcessAdapter:
    """Wrap a real subprocess so it matches the RendererProcessPool child API."""

    def __init__(self, popen: subprocess.Popen) -> None:
        self._popen = popen
        self.pid = popen.pid

    def is_alive(self) -> bool:
        return self._popen.poll() is None

    def join(self, timeout: float | None = None) -> None:
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._popen.wait(timeout=timeout)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Toolhelp32 / taskkill /T specific")
def test_windows_descendant_termination_kills_grandchild():
    with tempfile.TemporaryDirectory() as tmp:
        parent, grandchild = _spawn_stubborn_tree(Path(tmp))
        try:
            descendants = proc.descendant_pids(parent.pid)
            assert grandchild in descendants
            survivors = proc.terminate_process_tree(parent.pid, kill_timeout=5.0)
            assert survivors == set(), f"leaked descendants: {survivors}"
            assert not proc.is_alive(grandchild)
        finally:
            with contextlib.suppress(Exception):
                parent.wait(timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object specific")
def test_windows_job_object_kills_descendants_on_close():
    with tempfile.TemporaryDirectory() as tmp:
        parent, grandchild = _spawn_stubborn_tree(Path(tmp))
        job = proc.WindowsJob(0)
        try:
            assert job.active
            assert job.assign(parent.pid)
            # Closing the job handle must run the entire tree down.
            job.close()
            deadline = time.time() + 5
            while time.time() < deadline and proc.is_alive(grandchild):
                time.sleep(0.05)
            assert not proc.is_alive(grandchild)
        finally:
            with contextlib.suppress(Exception):
                proc.terminate_process_tree(parent.pid, kill_timeout=3.0)
                parent.wait(timeout=5)


def test_renderer_pool_reports_no_surviving_descendants():
    with tempfile.TemporaryDirectory() as tmp:
        parent, grandchild = _spawn_stubborn_tree(Path(tmp))
        pool = RendererProcessPool(kill_timeout=5.0)
        pool._process = _ProcessAdapter(parent)
        try:
            pool._terminate_process_tree()
            assert pool.last_survivors == set()
            assert not proc.is_alive(grandchild)
        finally:
            with contextlib.suppress(Exception):
                parent.wait(timeout=5)
