import pytest

"""
Tests for transactional, history-preserving batch reports and the stable
bridge error taxonomy.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch.reporting import write_batch_reports
from previewgen.errors import ErrorCode, classify_exception
from processor import PreviewConfig, process_folder

pytestmark = pytest.mark.core


def _summary(batch_id: str) -> dict:
    return {
        "batchId": batch_id,
        "finishedAt": "2026-01-01T00:00:00+00:00",
        "generationStatus": "completed",
    }


def test_reports_are_batch_versioned_and_latest_pointer_published():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)

        r1 = write_batch_reports(out, _summary("aaaa1111"), [])
        assert r1["status"] == "written"
        assert Path(r1["jsonPath"]).name == "previewgen-report-aaaa1111.json"
        assert Path(r1["csvPath"]).name == "previewgen-report-aaaa1111.csv"

        r2 = write_batch_reports(out, _summary("bbbb2222"), [])
        assert r2["status"] == "written"

        # History is preserved: both report pairs remain.
        assert (out / "previewgen-report-aaaa1111.json").is_file()
        assert (out / "previewgen-report-bbbb2222.json").is_file()

        latest = json.loads((out / "previewgen-report-latest.json").read_text(encoding="utf-8"))
        assert latest["batchId"] == "bbbb2222"
        assert latest["json"] == "previewgen-report-bbbb2222.json"
        assert latest["csv"] == "previewgen-report-bbbb2222.csv"


def test_reports_prune_beyond_retention():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for i in range(4):
            result = write_batch_reports(out, _summary(f"batch{i:04d}"), [], retention=2)
            p = Path(result["jsonPath"])
            os.utime(p, (1_000_000 + i, 1_000_000 + i))

        remaining = sorted(
            p.name for p in out.glob("previewgen-report-*.json")
            if p.name != "previewgen-report-latest.json"
        )
        assert remaining == ["previewgen-report-batch0002.json", "previewgen-report-batch0003.json"]
        # CSVs are pruned alongside their JSON.
        assert not (out / "previewgen-report-batch0000.csv").exists()
        assert (out / "previewgen-report-batch0002.csv").exists()


def test_report_write_failure_returns_stable_code():
    with tempfile.TemporaryDirectory() as tmp:
        # Point the "output folder" at a regular file so report writes must fail.
        bogus = Path(tmp) / "not_a_dir"
        bogus.write_text("x", encoding="utf-8")

        result = write_batch_reports(bogus, _summary("deadbeef"), [])
        assert result["status"] == "failed"
        assert result["errorCode"] == ErrorCode.REPORT_WRITE_FAILED


def test_classify_exception_maps_to_stable_codes():
    assert classify_exception(PermissionError("nope"))[0] == ErrorCode.PERMISSION_DENIED
    assert classify_exception(FileNotFoundError("gone"))[0] == ErrorCode.FOLDER_NOT_FOUND
    assert classify_exception(ModuleNotFoundError("No module named 'x'"))[0] == ErrorCode.RENDERER_MISSING
    assert classify_exception(TimeoutError("too slow"))[0] == ErrorCode.RENDER_TIMEOUT
    assert classify_exception(ValueError("Unknown configuration key(s): bogus"))[0] == ErrorCode.INVALID_CONFIGURATION
    assert (
        classify_exception(RuntimeError("Output directory is currently locked by another PreviewGen process"))[0]
        == ErrorCode.OUTPUT_LOCKED
    )
    assert classify_exception(ValueError("Source file exceeds maximum size limit"))[0] == ErrorCode.CORRUPT_ASSET
    assert (
        classify_exception(RuntimeError("Renderer error: cannot identify image file (UnidentifiedImageError)"))[0]
        == ErrorCode.CORRUPT_ASSET
    )
    assert classify_exception(Exception("kaboom"))[0] == ErrorCode.INTERNAL_ERROR


def test_batch_file_records_carry_error_codes():
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        in_dir = Path(tmp_in)
        out_dir = Path(tmp_out)

        # A valid asset plus a corrupt one with a supported extension.
        Image.new("RGBA", (40, 40), (0, 0, 255, 255)).save(in_dir / "good.png")
        (in_dir / "bad.png").write_bytes(b"not a real png")

        summary = process_folder(
            in_dir,
            out_dir,
            PreviewConfig(),
            progress=lambda c, t, s: None,
            is_cancelled=lambda: False,
        )

        by_source = {rec["source"]: rec for rec in summary["files"]}
        assert by_source["good.png"]["status"] == "success"
        assert by_source["bad.png"]["status"] == "failed"
        assert by_source["bad.png"]["errorCode"] == ErrorCode.CORRUPT_ASSET
