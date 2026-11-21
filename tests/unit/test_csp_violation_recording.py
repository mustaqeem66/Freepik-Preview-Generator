"""Tests for the packaged Content Security Policy violation recorder.

The native backend records what the frontend reports about policy violations.
That record is what the packaged Windows/macOS/Linux clean-machine runs assert
on, so it has to be accurate, bounded, and must never let a malformed report
from the renderer break the bridge.

Violations are written to `PREVIEWGEN_CSP_VIOLATIONS`; the self-test result
is written separately to `PREVIEWGEN_CSP_MARKER`, so the two records never
overwrite each other.
"""
from __future__ import annotations

import json

import pytest

from previewgen.api import DesktopApi


@pytest.fixture
def api() -> DesktopApi:
    return DesktopApi()


def test_violations_are_written_to_the_marker_as_json_lines(api, tmp_path, monkeypatch):
    marker = tmp_path / "csp.jsonl"
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(marker))

    result = api.report_csp_violations(
        [
            {
                "effectiveDirective": "script-src",
                "blockedURI": "https://example.invalid/x.js",
                "violatedDirective": "script-src 'self'",
                "resourceType": "script",
            },
            {
                "effectiveDirective": "connect-src",
                "blockedURI": "https://example.invalid/beacon",
                "violatedDirective": "connect-src 'self'",
                "resourceType": "xmlhttprequest",
            },
        ]
    )

    assert result["ok"] is True
    assert result["value"] == 2
    lines = marker.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["effectiveDirective"] == "script-src"
    assert first["blockedURI"] == "https://example.invalid/x.js"
    assert first["resourceType"] == "script"


def test_no_marker_file_is_created_without_violations(api, tmp_path, monkeypatch):
    marker = tmp_path / "csp.jsonl"
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(marker))

    result = api.report_csp_violations([])

    assert result["ok"] is True
    assert result["value"] == 0
    assert not marker.exists()


def test_malformed_entries_are_ignored_not_fatal(api, tmp_path, monkeypatch):
    marker = tmp_path / "csp.jsonl"
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(marker))

    result = api.report_csp_violations(
        [
            "not a dict",
            None,
            {"effectiveDirective": "img-src", "blockedURI": "https://example.invalid/a.png"},
        ]
    )

    assert result["ok"] is True
    assert result["value"] == 1
    recorded = json.loads(marker.read_text(encoding="utf-8").strip())
    assert recorded["effectiveDirective"] == "img-src"
    assert recorded["blockedURI"] == "https://example.invalid/a.png"
    # Missing fields become empty strings rather than KeyError.
    assert recorded["resourceType"] == ""


def test_the_report_is_bounded(api, tmp_path, monkeypatch):
    marker = tmp_path / "csp.jsonl"
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(marker))

    result = api.report_csp_violations(
        [{"blockedURI": f"https://example.invalid/{index}"} for index in range(500)]
    )

    assert result["value"] == 100
    assert len(marker.read_text(encoding="utf-8").strip().splitlines()) == 100


def test_a_missing_marker_directory_does_not_break_the_bridge(api, tmp_path, monkeypatch):
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(tmp_path / "absent" / "csp.jsonl"))

    result = api.report_csp_violations(
        [{"effectiveDirective": "script-src", "blockedURI": "https://example.invalid/x.js"}]
    )

    # The bridge must still answer, even when the evidence file cannot be written.
    assert result["ok"] is True
    assert result["value"] == 1


def test_a_non_list_report_is_rejected_safely(api, tmp_path, monkeypatch):
    marker = tmp_path / "csp.jsonl"
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(marker))

    result = api.report_csp_violations("not a list")  # type: ignore[arg-type]

    assert result["ok"] is True
    assert result["value"] == 0
    assert not marker.exists()


def test_violation_reports_do_not_modify_the_smoke_verdict(api, tmp_path, monkeypatch):
    violations = tmp_path / "csp_violations.jsonl"
    selftest = tmp_path / "csp_selftest.json"
    monkeypatch.setenv("PREVIEWGEN_CSP_VIOLATIONS", str(violations))
    monkeypatch.setenv("PREVIEWGEN_CSP_MARKER", str(selftest))
    verdict = {"inlineScript": "blocked", "blobScript": "blocked", "previewJpeg": "loaded"}
    selftest.write_text(json.dumps(verdict), encoding="utf-8")
    api.report_csp_violations(
        [{"effectiveDirective": "script-src", "blockedURI": "https://example.invalid/x.js"}]
    )
    assert json.loads(selftest.read_text(encoding="utf-8")) == verdict
    lines = violations.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["blockedURI"] == "https://example.invalid/x.js"
