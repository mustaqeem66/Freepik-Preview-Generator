import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processor import MAX_ZIP_MEMBERS, safe_extract_zip

pytestmark = pytest.mark.core


def test_zip_slip_path_traversal_blocked_unit():
    """Verify that safe_extract_zip blocks directory traversal attempts (../evil.png)."""
    with tempfile.TemporaryDirectory() as sandbox_dir, tempfile.TemporaryDirectory() as outside_dir:
        sandbox = Path(sandbox_dir)
        outside = Path(outside_dir)

        zip_path = sandbox / "traversal.zip"
        extract_dir = sandbox / "extracted"

        # Construct zip containing a valid file and an escape file
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("valid_doc.txt", b"Safe internal file")
            # Malicious path aiming to escape extract_dir into outside_dir
            zf.writestr("../outside_leak.txt", b"Exploit content")
            zf.writestr("../../escape.txt", b"Escape content")

        # Expect safe_extract_zip to reject the traversal attempt
        with pytest.raises(ValueError, match="Zip-Slip attempt"):
            safe_extract_zip(zip_path, extract_dir)

        # Confirm no files were written outside
        assert not (outside / "outside_leak.txt").exists()
        assert not (sandbox / "outside_leak.txt").exists()
        assert not (sandbox / "escape.txt").exists()


def test_zip_member_limit_enforced():
    """Verify that archives with excess entries are rejected."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        zip_path = tmp / "too_many_files.zip"
        extract_dir = tmp / "extracted"

        with zipfile.ZipFile(zip_path, "w") as zf:
            for i in range(MAX_ZIP_MEMBERS + 5):
                zf.writestr(f"file_{i}.txt", b"data")

        with pytest.raises(ValueError, match="Archive exceeds maximum member limit"):
            safe_extract_zip(zip_path, extract_dir)


def test_zip_declared_total_rejected_before_extraction(monkeypatch):
    """Verify the declared uncompressed total is rejected before extracting bytes."""
    import previewgen.batch.archive as archive_module

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        zip_path = tmp / "oversized.zip"
        extract_dir = tmp / "extracted"

        with zipfile.ZipFile(zip_path, "w") as zf:
            for i in range(3):
                zf.writestr(f"file_{i}.txt", b"12345")

        monkeypatch.setattr(archive_module.previewgen_config, "MAX_TOTAL_BYTES", 10)
        with pytest.raises(ValueError, match="Archive declares"):
            safe_extract_zip(zip_path, extract_dir)
        assert not extract_dir.exists() or not any(extract_dir.iterdir())


def test_valid_zip_extracts_correctly():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        zip_path = tmp / "normal.zip"
        extract_dir = tmp / "extracted"

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("folder/doc.txt", b"Hello world")
            zf.writestr("icon.png", b"fake png data")

        files = safe_extract_zip(zip_path, extract_dir)
        assert len(files) == 2
        assert (extract_dir / "folder" / "doc.txt").is_file()
        assert (extract_dir / "icon.png").is_file()
