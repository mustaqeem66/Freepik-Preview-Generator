"""Tests for the packaged Content Security Policy self-test.

The packaged app runs a self-test inside its own WebView and writes the
outcome to the marker file. A missing or contradictory verdict must fail.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "check_csp_marker.py"

spec = importlib.util.spec_from_file_location("check_csp_marker", MODULE_PATH)
assert spec and spec.loader
check_csp_marker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = check_csp_marker
spec.loader.exec_module(check_csp_marker)


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    marker = tmp_path / "csp.json"
    marker.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return marker


def test_both_script_blocks_and_decoded_jpeg_pass(tmp_path):
    marker = _write(tmp_path, {
        "inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "loaded",
    })
    assert check_csp_marker.main(["--marker", str(marker)]) == 0


def test_script_execution_fails_even_if_an_old_pass_flag_is_present(tmp_path):
    marker = _write(tmp_path, {
        "inlineScript": "blocked", "blobScript": "executed", "previewJpeg": "loaded",
        "externalBlocked": True,
    })
    assert check_csp_marker.main(["--marker", str(marker)]) == 1


def test_a_failed_preview_control_fails(tmp_path):
    marker = _write(tmp_path, {
        "inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "error",
    })
    assert check_csp_marker.main(["--marker", str(marker)]) == 1


def test_an_incomplete_probe_fails(tmp_path):
    marker = _write(tmp_path, {"inlineScript": "blocked", "blobScript": "blocked"})
    assert check_csp_marker.main(["--marker", str(marker)]) == 1


def test_a_missing_marker_is_an_error(tmp_path):
    assert check_csp_marker.main(["--marker", str(tmp_path / "absent.json")]) == 2


def test_an_empty_marker_is_an_error(tmp_path):
    marker = tmp_path / "csp.json"
    marker.write_text("", encoding="utf-8")
    assert check_csp_marker.main(["--marker", str(marker)]) == 2


def test_a_malformed_marker_is_an_error(tmp_path):
    marker = tmp_path / "csp.json"
    marker.write_text("not json", encoding="utf-8")
    assert check_csp_marker.main(["--marker", str(marker)]) == 2


def test_a_non_object_marker_is_an_error(tmp_path):
    marker = tmp_path / "csp.json"
    marker.write_text("[1, 2, 3]", encoding="utf-8")
    assert check_csp_marker.main(["--marker", str(marker)]) == 2
