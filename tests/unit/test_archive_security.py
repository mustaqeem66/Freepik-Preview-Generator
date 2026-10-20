import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch.archive import safe_extract_zip
from previewgen.config import MAX_ZIP_MEMBERS

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


def _write_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_nested_archives_unpacked_to_a_depth_cap(tmp_path):
    """Archive-in-archive is followed, but only to MAX_NESTED_DEPTH levels."""
    from previewgen.batch.runner import _extract_nested_archives

    third = _write_zip(tmp_path / "third.zip", {"deep.png": b"deep payload"})
    second = _write_zip(tmp_path / "second.zip", {"third.zip": third.read_bytes()})
    root = tmp_path / "extracted"
    root.mkdir()
    _write_zip(root / "first.zip", {"second.zip": second.read_bytes()})

    problems = _extract_nested_archives(root, lambda: False)

    assert (root / "first" / "second" / "third.zip").is_file()
    assert not (root / "first" / "second" / "third" / "deep.png").exists()
    assert len(problems) == 1 and "third.zip" in problems[0]


def test_nested_archives_share_one_byte_budget(tmp_path):
    """Each level must not get a fresh allowance or a nested bomb multiplies it."""
    from previewgen.batch.runner import _extract_nested_archives

    root = tmp_path / "extracted"
    root.mkdir()
    for name in ("one.zip", "two.zip"):
        _write_zip(root / name, {f"{name}.bin": b"x" * 4096})

    # Two 4 KiB archives but budget for one of them.
    problems = _extract_nested_archives(root, lambda: False, budget_bytes=6144)

    assert len(problems) == 1
    assert (root / "one").is_dir()
    assert not (root / "two").is_dir() or not (root / "two" / "two.zip.bin").exists()


def test_nested_archive_failures_are_reported_not_swallowed(tmp_path):
    from previewgen.batch.runner import _extract_nested_archives

    root = tmp_path / "extracted"
    root.mkdir()
    (root / "broken.zip").write_bytes(b"BM not really a zip file")

    problems = _extract_nested_archives(root, lambda: False)

    assert len(problems) == 1 and problems[0].startswith("broken.zip:")


def test_extraction_honours_cancellation(tmp_path):
    zip_path = tmp_path / "assets.zip"
    _write_zip(zip_path, {f"file_{i}.txt": b"data" for i in range(5)})
    extract_dir = tmp_path / "extracted"

    with pytest.raises(ValueError, match="cancelled"):
        safe_extract_zip(zip_path, extract_dir, is_cancelled=lambda: True)
    assert not any(extract_dir.iterdir()) if extract_dir.exists() else True

    from previewgen.batch.runner import _extract_nested_archives

    with pytest.raises(ValueError, match="cancelled"):
        _extract_nested_archives(tmp_path, lambda: True)
