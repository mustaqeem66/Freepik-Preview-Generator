"""Independent renderer-oracle evidence; no proprietary samples are invented."""
from __future__ import annotations

import hashlib
import json

import pytest
from PIL import Image

from scripts.audit_renderer_matrix import inspect_inventory, main, verify_samples

pytestmark = pytest.mark.core


def _gradient(path, shift: int = 0) -> None:
    image = Image.new("RGB", (64, 64))
    for x in range(64):
        for y in range(64):
            image.putpixel((x, y), ((x * 3 + shift) % 256, y * 3, (x + y) * 2))
    image.save(path)


def _manifest(approved, source_version="ExampleCAD 2.1", error=5.0):
    return {"samples": [{
        "file": "part.png",
        "sourceApp": "ExampleCAD",
        "sourceVersion": source_version,
        "oracle": {
            "image": approved.name,
            "sha256": hashlib.sha256(approved.read_bytes()).hexdigest(),
            "reviewedBy": "Design QA",
            "maxMeanAbsoluteError": error,
        },
    }]}


def test_independent_approved_oracle_matches_isolated_renderer(tmp_path, monkeypatch):
    from previewgen import renderer_process

    source = tmp_path / "part.png"
    approved = tmp_path / "approved.png"
    _gradient(source)
    _gradient(approved)
    manifest = _manifest(approved)
    report = inspect_inventory(manifest, tmp_path)

    def fake_renderer(_src, output, _cfg, timeout_seconds):
        assert timeout_seconds == 2.0
        Image.open(source).save(output, "JPEG", quality=100)

    monkeypatch.setattr(renderer_process, "render_file_isolated", fake_renderer)
    verify_samples(report, tmp_path, timeout=2.0)
    sample = report["samples"][0]
    assert sample["status"] == "passed"
    assert sample["oracleStatus"] == "matched"
    assert sample["fidelityVerified"] is True
    assert sample["oracleMeanAbsoluteError"] <= 5
    assert sample["sourcePreserved"] is True
    assert sample["sourceVersion"] == "ExampleCAD 2.1"


def test_wrong_render_with_many_colors_fails_oracle_comparison(tmp_path, monkeypatch):
    from previewgen import renderer_process

    source = tmp_path / "part.png"
    approved = tmp_path / "approved.png"
    _gradient(source)
    _gradient(approved)
    report = inspect_inventory(_manifest(approved, error=3), tmp_path)

    def fake_renderer(_src, output, _cfg, timeout_seconds):
        other = tmp_path / "wrong.png"
        _gradient(other, shift=90)
        Image.open(other).save(output, "JPEG", quality=100)

    monkeypatch.setattr(renderer_process, "render_file_isolated", fake_renderer)
    verify_samples(report, tmp_path, timeout=2.0)
    sample = report["samples"][0]
    assert sample["status"] == "failed"
    assert sample["oracleStatus"] == "failed"
    assert sample["fidelityVerified"] is False
    assert "Fidelity error" in sample["failure"]


def test_tampered_oracle_reference_fails_closed(tmp_path, monkeypatch):
    from previewgen import renderer_process

    source = tmp_path / "part.png"
    approved = tmp_path / "approved.png"
    _gradient(source)
    _gradient(approved)
    manifest = _manifest(approved)
    # The audited oracle must NOT be silently replaced by a new file.
    approved.write_bytes(b"tampered")
    report = inspect_inventory(manifest, tmp_path)
    monkeypatch.setattr(
        renderer_process, "render_file_isolated",
        lambda _src, output, _cfg, timeout_seconds: Image.open(source).save(output, "JPEG"),
    )
    verify_samples(report, tmp_path, timeout=2.0)
    assert report["samples"][0]["status"] == "failed"
    assert "SHA-256" in report["samples"][0]["failure"]


@pytest.mark.parametrize("corruption", [
    {"image": "../private.png"},
    {"image": "/tmp/reference.png"},
    {"image": "not-image.txt"},
    {"image": "C:\\private.png"},
    {"sha256": "invalid"},
    {"reviewedBy": ""},
    {"maxMeanAbsoluteError": -1},
    {"maxMeanAbsoluteError": True},
])
def test_invalid_oracle_contract_rejected_before_render(tmp_path, corruption):
    source = tmp_path / "part.png"
    approved = tmp_path / "approved.png"
    _gradient(source)
    _gradient(approved)
    manifest = _manifest(approved)
    manifest["samples"][0]["oracle"].update(corruption)
    with pytest.raises(ValueError):
        inspect_inventory(manifest, tmp_path)


def test_oracle_requires_declared_authoring_application_version(tmp_path):
    source = tmp_path / "part.png"
    approved = tmp_path / "approved.png"
    _gradient(source)
    _gradient(approved)
    with pytest.raises(ValueError, match="sourceVersion"):
        inspect_inventory(_manifest(approved, source_version=""), tmp_path)


def test_require_oracles_never_certifies_smoke_only_render(tmp_path, monkeypatch):
    from previewgen import renderer_process

    source = tmp_path / "part.png"
    _gradient(source)
    manifest = tmp_path / "samples.json"
    manifest.write_text(json.dumps({"samples": [{"file": "part.png"}]}))
    report_path = tmp_path / "audit.json"
    monkeypatch.setattr(
        renderer_process, "render_file_isolated",
        lambda _src, output, _cfg, timeout_seconds: Image.open(source).save(output, "JPEG", quality=90),
    )
    assert main(["--manifest", str(manifest), "--report", str(report_path),
                 "--require-oracles", "--timeout", "2"]) == 1
    result = json.loads(report_path.read_text())
    assert result["runMode"] == "isolated_render"
    assert result["samples"][0]["status"] == "passed"
    assert result["samples"][0]["fidelityVerified"] is False
    assert result["registry"]["oracleVerifiedFixtures"] == 0
