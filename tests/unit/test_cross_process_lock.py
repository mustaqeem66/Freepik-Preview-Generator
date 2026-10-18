import pytest

"""
Cross-process output-directory locking.

Synchronization is fully deterministic: the lock holder signals readiness over a
pipe and then blocks on stdin until the parent explicitly releases it. No test
relies on ``time.sleep`` to order inter-process events, so the assertions cannot
flake on slow or heavily loaded machines.

Two independent properties are covered:

1. ``test_lock_primitive_is_exclusive_across_processes`` exercises the raw file
   lock (``flock`` / ``msvcrt.locking``) in isolation.
2. ``test_process_folder_rejects_locked_output_directory`` exercises the
   production integration point: ``process_folder`` must refuse to run while
   another process holds the output-directory lock, and must succeed once it is
   released.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

READY = "READY"
RELEASE = "RELEASE"

# Exit codes used by the helper subprocesses.
_ACQUIRED = 0
_LOCKED = 42


def _acquire_lock_source(indent: str) -> list[str]:
    """Statements that acquire an exclusive lock via the centralized DirectoryLock service."""
    i = indent
    return [
        f"{i}sys.path.insert(0, r'{PROJECT_ROOT}')",
        f"{i}from previewgen.lock import DirectoryLock, DirectoryLockError",
        f"{i}dir_lock = DirectoryLock(lock_file.parent)",
        f"{i}dir_lock.acquire()",
    ]


def _spawn_lock_holder(lock_file: Path) -> subprocess.Popen:
    """Start a process that holds the exclusive lock until explicitly released.

    The holder prints ``READY`` once the lock is held, then blocks reading stdin
    until the parent writes ``RELEASE``. This makes the holder's lock lifetime
    deterministic regardless of how long the contender takes to boot.
    """
    holder_code = "\n".join([
        "import sys",
        "from pathlib import Path",
        f"lock_file = Path(r'{lock_file}')",
        *_acquire_lock_source(""),
        "sys.stdout.write('READY\\n')",
        "sys.stdout.flush()",
        "sys.stdin.readline()",
        "dir_lock.release()",
        "sys.exit(0)",
    ])
    return subprocess.Popen(
        [sys.executable, "-c", holder_code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )


def _wait_until_ready(proc: subprocess.Popen) -> None:
    line = proc.stdout.readline() if proc.stdout else ""
    assert READY in line, f"lock holder failed to acquire the lock (output: {line!r})"


def _release(proc: subprocess.Popen) -> None:
    if proc.stdin:
        proc.stdin.write(RELEASE + "\n")
        proc.stdin.flush()
    proc.wait(timeout=30)
    if proc.stdin:
        proc.stdin.close()
    if proc.stdout:
        proc.stdout.close()


def _attempt_raw_lock(lock_file: Path) -> int:
    """Try the raw file lock from a separate process; return its exit code."""
    attempt_code = "\n".join([
        "import sys",
        "from pathlib import Path",
        f"lock_file = Path(r'{lock_file}')",
        "try:",
        *_acquire_lock_source("    "),
        f"    sys.exit({_ACQUIRED})",
        "except (BlockingIOError, OSError, DirectoryLockError):",
        f"    sys.exit({_LOCKED})",
    ])
    return subprocess.run([sys.executable, "-c", attempt_code]).returncode


def _attempt_process_folder(input_dir: Path, output_dir: Path) -> int:
    """Run ``process_folder`` in a separate process; return its exit code."""
    attempt_code = "\n".join([
        "import sys",
        "from pathlib import Path",
        f"sys.path.insert(0, r'{PROJECT_ROOT}')",
        "from processor import process_folder, PreviewConfig",
        "try:",
        "    process_folder(",
        f"        Path(r'{input_dir}'),",
        f"        Path(r'{output_dir}'),",
        "        PreviewConfig(),",
        "        lambda current, total, status: None,",
        "        lambda: False,",
        "    )",
        f"    sys.exit({_ACQUIRED})",
        "except RuntimeError as exc:",
        "    if 'locked by another' in str(exc):",
        f"        sys.exit({_LOCKED})",
        "    sys.exit(1)",
    ])
    return subprocess.run([sys.executable, "-c", attempt_code]).returncode


def test_lock_primitive_is_exclusive_across_processes():
    """The raw file lock is mutually exclusive and is released on exit."""
    with tempfile.TemporaryDirectory() as tmp:
        lock_file = Path(tmp) / ".previewgen.lock"

        holder = _spawn_lock_holder(lock_file)
        try:
            _wait_until_ready(holder)
            assert _attempt_raw_lock(lock_file) == _LOCKED, (
                "a second process acquired a lock that was already held"
            )
        finally:
            _release(holder)

        # Once the holder has exited the lock must be free again.
        assert _attempt_raw_lock(lock_file) == _ACQUIRED, (
            "the lock was still held after the holder process exited"
        )


def test_process_folder_rejects_locked_output_directory():
    """``process_folder`` refuses a locked output dir, then succeeds once freed."""
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        in_p = Path(tmp_in)
        out_p = Path(tmp_out)
        Image.new("RGBA", (100, 100), (0, 0, 255, 255)).save(in_p / "img.png")

        holder = _spawn_lock_holder(out_p / ".previewgen.lock")
        try:
            _wait_until_ready(holder)
            assert _attempt_process_folder(in_p, out_p) == _LOCKED, (
                "process_folder did not raise the 'locked by another' error"
            )
        finally:
            _release(holder)

        # With the lock released the same batch must run to completion.
        assert _attempt_process_folder(in_p, out_p) == _ACQUIRED, (
            "process_folder failed after the output-directory lock was released"
        )
        # Inode-race prevention: lock file must remain permanently in place.
        assert (out_p / ".previewgen.lock").exists(), (
            "lock file was unlinked on release (must be kept permanently to prevent inode races)"
        )

def test_directory_lock_service_metadata_and_persistence(tmp_path):
    """DirectoryLock must write owner metadata, preserve the file on release, and support context manager."""
    import os

    from previewgen.lock import LOCK_FILENAME, DirectoryLock

    out_dir = tmp_path / "locked_out"
    out_dir.mkdir()

    with DirectoryLock(out_dir, batch_id="batch_meta_123") as lock:
        assert lock.is_acquired
        meta = lock.read_metadata()
        assert meta is not None
        assert meta.get("pid") == os.getpid()
        assert meta.get("batchId") == "batch_meta_123"
        assert "startedAt" in meta

    # File must persist permanently on disk to prevent inode races
    assert (out_dir / LOCK_FILENAME).exists()

    # Re-acquisition on the exact same directory must succeed immediately
    second_lock = DirectoryLock(out_dir, batch_id="batch_meta_456")
    assert second_lock.acquire() is True
    second_lock.release()
    assert (out_dir / LOCK_FILENAME).exists()
