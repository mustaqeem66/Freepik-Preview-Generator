"""Native release gate requires concrete, independently recorded local evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.native_release_evidence import (
    PLATFORM_GATES,
    file_sha256,
    main,
    required_gates,
    start_receipt,
    validate_receipt,
)

pytestmark = pytest.mark.core

SOURCE_SHA = "a" * 40


@pytest.mark.parametrize("platform", list(PLATFORM_GATES))
def test_no_native_platform_receipt_self_certifies(tmp_path: Path, platform: str):
    binary = tmp_path / ("previewgen.exe" if platform == "windows" else "previewgen.app")
    binary.write_bytes(b"fake unsigned binary\x00")
    receipt = start_receipt(platform, SOURCE_SHA, binary)
    assert set(receipt["gates"]) == set(required_gates(platform))
    assert all(gate["status"] == "pending" for gate in receipt["gates"].values())
    assert receipt["artifact"]["sha256"] == file_sha256(binary)
    assert validate_receipt(receipt, binary, tmp_path)


def test_verified_receipt_rejects_tampering_and_missing_evidence(tmp_path: Path):
    binary = tmp_path / "previewgen.exe"
    binary.write_bytes(b"fake packaged binary")
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()

    receipt = start_receipt("windows", SOURCE_SHA, binary)
    receipt["reviewer"] = "Human reviewer"
    evidence_paths = []
    for index, gate in enumerate(receipt["gates"].values()):
        evidence = evidence_dir / f"native-qa-{index:02d}.txt"
        evidence.write_text(
            f"Human verified native packaged application gate {index}, TEST placeholder",
            encoding="utf-8",
        )
        gate.update({"status": "passed", "evidenceFile": evidence.name,
                     "evidenceSha256": file_sha256(evidence)})
        evidence_paths.append(evidence)

    assert validate_receipt(receipt, binary, evidence_dir) == []

    binary.write_bytes(b"different binary")
    assert any("artifact" in issue for issue in validate_receipt(receipt, binary, evidence_dir))

    binary.write_bytes(b"fake packaged binary")
    evidence_paths[0].write_bytes(b"modified evidence")
    assert any("evidence" in issue for issue in validate_receipt(receipt, binary, evidence_dir))


def test_absolute_or_parent_evidence_paths_are_denied(tmp_path: Path):
    binary = tmp_path / "app.exe"
    binary.write_bytes(b"x")
    receipt = start_receipt("linux", SOURCE_SHA, binary)
    receipt["reviewer"] = "QA"
    for gate in receipt["gates"].values():
        gate.update({"status": "passed", "evidenceFile": "../hidden",
                     "evidenceSha256": "0" * 64})
    errors = validate_receipt(receipt, binary, tmp_path)
    assert any("safe basename" in error for error in errors)


def test_windows_requires_signature_proof_not_unsigned_exception(tmp_path: Path):
    binary = tmp_path / "PreviewGen-Setup.exe"
    binary.write_bytes(b"test binary")
    receipt = start_receipt("windows", SOURCE_SHA, binary)
    required = set(receipt["gates"])
    assert "windows_authenticode_signature_verified_for_release" in required
    assert not any("untrusted_status" in name for name in required)
    assert validate_receipt(receipt, binary, tmp_path)


def test_command_line_check_fails_with_pending_results(tmp_path: Path):
    artifact = tmp_path / "artifact.AppImage"
    artifact.write_bytes(b"fake AppImage")
    receipt_path = tmp_path / "receipt.json"
    assert main(["init", "--platform", "linux", "--commit", SOURCE_SHA,
                 "--artifact", str(artifact), "--output", str(receipt_path)]) == 0
    saved = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert saved["platform"] == "linux"
    assert main(["verify", "--receipt", str(receipt_path),
                 "--artifact", str(artifact), "--evidence-dir", str(tmp_path)]) == 1
    # Prevent evidence loss from accidental command reruns.
    assert main(["init", "--platform", "linux", "--commit", SOURCE_SHA,
                 "--artifact", str(artifact), "--output", str(receipt_path)]) == 1

def _approved_test_receipt(tmp_path: Path):
    artifact = tmp_path / "app.exe"
    artifact.write_bytes(b"package fixture")
    folder = tmp_path / "qa"
    folder.mkdir()
    receipt = start_receipt("windows", SOURCE_SHA, artifact)
    receipt["reviewer"] = "Local QA"
    for index, gate in enumerate(receipt["gates"].values()):
        file = folder / f"gate-{index}.txt"
        file.write_text(f"Recorded evidence for test gate {index}", encoding="utf-8")
        gate.update({
            "status": "passed", "evidenceFile": file.name,
            "evidenceSha256": file_sha256(file),
        })
    assert validate_receipt(receipt, artifact, folder) == []
    return artifact, folder, receipt


def test_one_placeholder_cannot_satisfy_every_native_gate(tmp_path: Path):
    artifact, folder, receipt = _approved_test_receipt(tmp_path)
    gates = list(receipt["gates"].values())
    for gate in gates[1:]:
        gate["evidenceFile"] = gates[0]["evidenceFile"]
        gate["evidenceSha256"] = gates[0]["evidenceSha256"]
    reasons = validate_receipt(receipt, artifact, folder)
    assert any("reused by another gate" in failure for failure in reasons)


def test_empty_or_linked_gate_evidence_must_fail(tmp_path: Path):
    artifact, folder, receipt = _approved_test_receipt(tmp_path)
    gate = next(iter(receipt["gates"].values()))
    file = folder / gate["evidenceFile"]
    file.write_bytes(b"")
    gate["evidenceSha256"] = file_sha256(file)
    assert any("empty" in error for error in validate_receipt(receipt, artifact, folder))

    external = tmp_path / "outside.txt"
    external.write_text("External QA file", encoding="utf-8")
    file.unlink()
    try:
        file.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("This OS account does not permit creating symlinks")
    gate["evidenceSha256"] = file_sha256(external)
    assert any("symbolic link" in error for error in validate_receipt(receipt, artifact, folder))
