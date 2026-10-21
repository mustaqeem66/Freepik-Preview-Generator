"""Truthful renderer-format capability catalog and fixture inventory."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from previewgen.assets import probe_asset
from previewgen.config import SUPPORTED_EXTENSIONS
from previewgen.renderers.capabilities import CAPABILITIES, capability_for, validate_registry
from scripts.audit_renderer_matrix import inspect_inventory, verify_samples

pytestmark = pytest.mark.core


def test_every_advertised_extension_has_explicit_capability():
    assert validate_registry() == (set(), set())
    assert set(CAPABILITIES) == set(SUPPORTED_EXTENSIONS)
    assert capability_for(".DWG").mode == "embedded"
    assert capability_for(".glb").mode == "mesh"
    assert capability_for(".step").mode == "cad"
    assert capability_for(".blend").mode == "external_fallback"
    assert capability_for(".zip").mode == "container"
    assert capability_for(".totallyunknown") is None


def test_probe_describes_preview_method_without_claiming_universal_support(tmp_path):
    file = tmp_path / "art.png"
    Image.new("RGBA", (32, 32), "red").save(file)
    result = probe_asset(file)
    assert result["previewSupport"]["mode"] == "raster"
    assert result["previewSupport"]["engines"] == ("PIL",)


def test_inventory_reports_missing_evidence_without_fabricating_success(tmp_path):
    file = tmp_path / "sample.png"
    Image.new("RGB", (32, 32), "blue").save(file)
    report = inspect_inventory({
        "samples": [
            {"file": "sample.png", "sourceApp": "test"},
            {"file": "sample.dwg", "sourceApp": "AutoCAD"},
        ]
    }, tmp_path)
    assert report["registry"]["coverageComplete"] is False
    assert report["registry"]["formatsWithPresentFixtures"] == 1
    assert ".dwg" in report["registry"]["formatsWithoutFixtures"]
    assert report["samples"][0]["status"] == "not_run"
    assert report["samples"][1]["status"] == "missing_fixture"


def test_inventory_rejects_manifest_traversal_and_unpreviewable_archive(tmp_path):
    for name in ("../private.png", "bundle.zip", "/tmp/private.obj"):
        with pytest.raises(ValueError):
            inspect_inventory({"samples": [{"file": name}]}, tmp_path)


def test_isolated_fixture_audit_measures_jpeg_and_source_immutability(tmp_path, monkeypatch):
    from previewgen import renderer_process

    source = tmp_path / "sample.png"
    Image.new("RGB", (32, 32), "red").save(source)
    before = source.read_bytes()
    report = inspect_inventory({"samples": [{"file": "sample.png"}]}, tmp_path)

    def fake_render(src, dest, _config, timeout_seconds):
        assert src == source
        assert timeout_seconds == 2.0
        colored = Image.new("RGB", (64, 64))
        for x in range(64):
            for y in range(64):
                colored.putpixel((x, y), (x * 3, y * 3, x + y))
        colored.save(dest, "JPEG")

    monkeypatch.setattr(renderer_process, "render_file_isolated", fake_render)
    verify_samples(report, tmp_path, timeout=2.0)
    assert report["samples"][0]["status"] == "passed"
    assert report["samples"][0]["sourcePreserved"] is True
    assert report["samples"][0]["outputSize"] == [64, 64]
    assert source.read_bytes() == before


def test_repository_manifest_has_real_known_baselines_and_no_fake_full_coverage():
    manifest_path = Path(__file__).resolve().parents[1] / "fixtures" / "renderer-samples.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = inspect_inventory(manifest, manifest_path.parent)
    assert len(report["samples"]) >= 9
    assert report["registry"]["coverageComplete"] is False
    assert report["registry"]["advertisedWithoutCapability"] == []

def test_audit_reports_source_deleted_by_renderer_instead_of_crashing(tmp_path, monkeypatch):
    from previewgen import renderer_process

    source = tmp_path / "sample.png"
    Image.new("RGB", (32, 32), "green").save(source)
    report = inspect_inventory({"samples": [{"file": "sample.png"}]}, tmp_path)

    def destructive_render(src, _dest, _config, timeout_seconds):
        src.unlink()
        raise RuntimeError("failed after deleting source")

    monkeypatch.setattr(renderer_process, "render_file_isolated", destructive_render)
    verify_samples(report, tmp_path, timeout=1.0)
    entry = report["samples"][0]
    assert entry["status"] == "source_modified"
    assert entry["sourcePreserved"] is False
    assert entry["sourceIntegrityError"] == "FileNotFoundError"


def test_strict_flag_always_runs_renderer_even_with_present_fixture(tmp_path, monkeypatch):
    from scripts import audit_renderer_matrix

    file = tmp_path / "sample.png"
    Image.new("RGB", (32, 32), "blue").save(file)
    manifest = tmp_path / "samples.json"
    manifest.write_text(json.dumps({"samples": [{"file": "sample.png"}]}), encoding="utf-8")
    report_file = tmp_path / "result.json"
    recorded = []

    def fake_verify(report, directory, timeout):
        recorded.append((directory, timeout))
        report["runMode"] = "isolated_render"
        report["samples"][0]["status"] = "failed"

    monkeypatch.setattr(audit_renderer_matrix, "verify_samples", fake_verify)
    assert audit_renderer_matrix.main([
        "--manifest", str(manifest), "--report", str(report_file), "--strict"
    ]) == 1
    assert len(recorded) == 1
    saved = json.loads(report_file.read_text(encoding="utf-8"))
    assert saved["runMode"] == "isolated_render"
    assert saved["samples"][0]["status"] == "failed"
