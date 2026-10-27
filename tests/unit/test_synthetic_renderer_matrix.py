"""Deterministic smoke samples supplement—but never replace—visual oracles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_renderer_matrix import inspect_inventory
from scripts.generate_synthetic_renderer_matrix import BASE_FIXTURES, generate

pytestmark = pytest.mark.core


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generated_smoke_matrix_is_reproducible_and_has_25_or_more_formats(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    report = generate(first)
    assert report["uniqueExtensions"] >= 25
    assert report["generatedFiles"] >= 19

    manifest = json.loads((first / "renderer-samples.json").read_text(encoding="utf-8"))
    catalog = inspect_inventory(manifest, first)
    assert catalog["registry"]["formatsWithPresentFixtures"] >= 25
    assert not catalog["registry"]["coverageComplete"], (
        "Synthetic smoke fixtures must not be mistaken for complete certification"
    )
    assert all(not sample["fidelityVerified"] for sample in catalog["samples"])

    # Deliberately omit all oracle references. A synthetic output must never
    # become the reference image used to certify the same renderer.
    assert all("oracle" not in item for item in manifest["samples"])
    assert any(item["sourceApp"].startswith("PreviewGen deterministic synthetic")
               for item in manifest["samples"])

    generate(second)
    originals = sorted(p.name for p in first.iterdir() if p.is_file())
    regenerated = sorted(p.name for p in second.iterdir() if p.is_file())
    assert originals == regenerated
    for name in originals:
        assert _sha(first / name) == _sha(second / name), name


def test_existing_fixtures_are_copied_without_mutation(tmp_path):
    target = tmp_path / "copy"
    generate(target)
    fixture = BASE_FIXTURES / "sample.png"
    assert _sha(fixture) == _sha(target / "sample.png")


def test_generator_refuses_to_overwrite_bundled_fixture_directory():
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        generate(BASE_FIXTURES)


def test_gltf_smoke_has_integrated_buffer_and_no_external_fetch(tmp_path):
    target = tmp_path / "gltf"
    generate(target)
    item = json.loads((target / "synthetic.gltf").read_text(encoding="utf-8"))
    assert item["asset"]["version"] == "2.0"
    assert item["buffers"][0]["uri"].startswith("data:application/octet-stream;base64,")
    assert len(item["meshes"]) == 1
