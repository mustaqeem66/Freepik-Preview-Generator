"""
A truncated scan/discovery must never be reported as a plain success.

Commercial batch processing may legitimately stop early at a safety limit, but
the result must say so explicitly: ``completed_with_warnings`` plus
``truncated`` / ``truncationReasons`` / ``discovered`` so the UI can require the
operator to acknowledge that not every file was processed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import previewgen.scanner as scanner_module
from previewgen.scanner import ScannerService
from processor import PreviewConfig, process_folder

pytestmark = pytest.mark.core


def test_batch_reports_completed_with_warnings_when_truncated(tmp_path, monkeypatch):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    for i in range(5):
        Image.new("RGBA", (24, 24), (12, 34, 200, 255)).save(in_dir / f"img{i}.png")

    monkeypatch.setattr("previewgen.batch.runner.DISCOVERY_MAX_FILES", 2)

    summary = process_folder(
        in_dir,
        out_dir,
        PreviewConfig(),
        progress=lambda c, t, s: None,
        is_cancelled=lambda: False,
    )

    assert summary["status"] == "completed_with_warnings"
    assert summary["generationStatus"] == "completed_with_warnings"
    assert summary["truncated"] is True
    assert summary["truncationReasons"] == ["maximum_files"]
    assert summary["discovered"] == 2
    assert summary["success"] == 2
    assert summary["processed"] == 2


def test_batch_reports_plain_completed_when_not_truncated(tmp_path):
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    Image.new("RGBA", (24, 24), (12, 34, 200, 255)).save(in_dir / "only.png")

    summary = process_folder(
        in_dir,
        out_dir,
        PreviewConfig(),
        progress=lambda c, t, s: None,
        is_cancelled=lambda: False,
    )

    assert summary["status"] == "completed"
    assert summary["truncated"] is False
    assert summary["truncationReasons"] == []


def test_scanner_reports_truncated_status_with_reasons(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    root.mkdir()
    for i in range(5):
        (root / f"a{i}.png").write_bytes(b"x")

    monkeypatch.setattr(scanner_module, "MAX_SCAN_ITEMS", 2)

    result = ScannerService().scan_folder(str(root))

    assert result["truncated"] is True
    assert "maximum_files" in result["truncationReasons"]
    assert len(result["files"]) == 2


def test_scanner_reports_completed_without_truncation(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    (root / "one.png").write_bytes(b"x")

    result = ScannerService().scan_folder(str(root))

    assert result["truncated"] is False
    assert result["truncationReasons"] == []
    assert len(result["files"]) == 1

def test_batch_reports_completed_with_warnings_on_permission_error(tmp_path, monkeypatch):
    """When directory discovery encounters permission errors, report completed_with_warnings."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    Image.new("RGBA", (24, 24), (12, 34, 200, 255)).save(in_dir / "accessible.png")

    def mock_discover_files(*args, **kwargs):
        stats = kwargs.get("stats")
        if stats:
            stats.permission_errors = 1
            stats.inaccessible_directories.append("restricted_folder")
            stats.truncated = True
            stats.reasons.append("permission_denied")
        yield in_dir / "accessible.png"

    monkeypatch.setattr("previewgen.batch.runner.discover_files", mock_discover_files)

    summary = process_folder(
        in_dir,
        out_dir,
        PreviewConfig(),
        progress=lambda c, t, s: None,
        is_cancelled=lambda: False,
    )

    assert summary["status"] == "completed_with_warnings"
    assert summary["discoveryPermissionErrors"] == 1
    assert "restricted_folder" in summary["inaccessibleDirectories"]
    # Sensitive absolute path must not leak into inaccessibleDirectories
    assert not any(str(in_dir) in p for p in summary["inaccessibleDirectories"])


def test_scanner_reports_completed_with_warnings_on_permission_error(tmp_path, monkeypatch):
    """Scanner must set status=completed_with_warnings and provide safe relative paths on permission denial."""
    root = tmp_path / "assets"
    root.mkdir()
    (root / "valid.png").write_bytes(b"x")

    # Simulate an unreadable subfolder triggering os.walk onerror
    def mock_walk(top, topdown=True, onerror=None, followlinks=False):
        yield str(top), ["locked_dir"], ["valid.png"]
        if onerror:
            err = PermissionError(13, "Permission denied")
            err.filename = str(Path(top) / "locked_dir")
            onerror(err)

    monkeypatch.setattr("os.walk", mock_walk)

    result = ScannerService().scan_folder(str(root))
    assert result["status"] == "completed_with_warnings"
    assert result["permissionErrors"] == 1
    assert "locked_dir" in result["inaccessibleDirectories"]
    assert result["remediation"] is not None
