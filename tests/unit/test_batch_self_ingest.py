"""A same-folder batch must not ingest the previews it wrote on an earlier run.

Reproduces the growth reported on the audit: exporting into the picked folder
made the next run treat its own output as a new source, so each run planned
more work than the last (1 -> 3 -> 7) forever.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch.discovery import DiscoveryLimits, discover_files
from previewgen.batch.reporting import previously_generated_outputs
from previewgen.config import SUPPORTED_EXTENSIONS
from processor import PreviewConfig, process_folder

pytestmark = pytest.mark.core


def _seed_jpg(path: Path) -> None:
    Image.new("RGB", (120, 90), (200, 30, 30)).save(path, "JPEG")


def _run(folder: Path) -> dict:
    return process_folder(
        folder,
        folder,
        PreviewConfig.from_mapping({"overwritePolicy": "skip"}),
        progress=lambda *args: None,
        is_cancelled=lambda: False,
    )


def test_repeated_same_folder_runs_do_not_grow(tmp_path: Path):
    source = tmp_path / "holiday.jpg"
    _seed_jpg(source)

    for run in range(1, 5):
        summary = _run(tmp_path)
        assert summary["discovered"] == 1, f"run {run}: {summary}"
        assert summary["planned"] == 1, f"run {run}: {summary}"
        assert summary["success"] + summary["skipped"] == 1
        assert summary["failed"] == 0
        # A re-ingested preview would watermark a watermark.
        assert not list(tmp_path.glob("*preview_preview*"))
        assert not list(tmp_path.glob("*_copy*"))

    assert Image.open(source).size == (120, 90)


def test_prior_report_lists_the_generated_preview(tmp_path: Path):
    source = tmp_path / "a.jpg"
    _seed_jpg(source)
    summary = _run(tmp_path)

    assert summary["success"] == 1
    generated = (tmp_path / summary["files"][0]["output"]).resolve()
    assert previously_generated_outputs(tmp_path) == {generated}


def test_unreadable_reports_are_ignored_not_fatal(tmp_path: Path):
    _seed_jpg(tmp_path / "a.jpg")
    summary = _run(tmp_path)
    good = previously_generated_outputs(tmp_path)
    assert good

    report = tmp_path / summary["reportJson"]
    assert report.name != "previewgen-report-latest.json"
    report.write_text("{not json", encoding="utf-8")
    assert previously_generated_outputs(tmp_path) == set()

    report.write_text(json.dumps({"files": [{"output": 42}, "nope", {"output": ""}]}), encoding="utf-8")
    assert previously_generated_outputs(tmp_path) == set()
    assert summary["reportStatus"] == "written"


def test_discovery_excludes_named_paths_only(tmp_path: Path):
    keep = tmp_path / "keep.jpg"
    drop = tmp_path / "drop.jpg"
    _seed_jpg(keep)
    _seed_jpg(drop)

    found = list(
        discover_files(
            tmp_path,
            is_cancelled=lambda: False,
            excluded_roots=(),
            limits=DiscoveryLimits(),
            supported_extensions=SUPPORTED_EXTENSIONS,
            excluded_paths={drop.resolve()},
        )
    )

    assert [p.name for p in found] == ["keep.jpg"]
