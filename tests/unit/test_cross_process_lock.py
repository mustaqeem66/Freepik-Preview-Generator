import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_cross_process_directory_lock():
    """Verify cross-process output directory locking across separate OS processes."""
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        in_p = Path(tmp_in)
        out_p = Path(tmp_out)

        Image.new("RGBA", (100, 100), (0, 0, 255, 255)).save(in_p / "img.png")

        # Spawn a subprocess that holds the lock file for 3 seconds
        lock_holder_code = f"""
import sys, time
from pathlib import Path
out_dir = Path(r'{out_p}')
out_dir.mkdir(parents=True, exist_ok=True)
lock_file = out_dir / '.previewgen.lock'
f = open(lock_file, 'w')
if sys.platform != 'win32':
    import fcntl
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
else:
    import msvcrt
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

print('LOCKED', flush=True)
time.sleep(2.5)
"""
        proc = subprocess.Popen([sys.executable, "-c", lock_holder_code], stdout=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline() if proc.stdout else ""
            assert "LOCKED" in line

            # Second process attempting to process_folder against out_p must immediately fail
            attempt_code = f"""
import sys
from pathlib import Path
sys.path.insert(0, r'{PROJECT_ROOT}')
from processor import process_folder, PreviewConfig

try:
    process_folder(Path(r'{in_p}'), Path(r'{out_p}'), PreviewConfig(), lambda c,t,s: None, lambda: False)
    sys.exit(0)
except RuntimeError as e:
    if 'locked by another' in str(e):
        sys.exit(42)
    sys.exit(1)
"""
            sub_attempt = subprocess.run([sys.executable, "-c", attempt_code])
            assert sub_attempt.returncode == 42, f"Expected returncode 42 (locked), got {sub_attempt.returncode}"
        finally:
            proc.kill()
            proc.wait()
