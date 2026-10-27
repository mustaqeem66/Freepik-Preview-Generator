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
    evidence = evidence_dir / "native-qa.txt"
    evidence.write_text("Human verified native packaged application, placeholder TEST", encoding="utf-8")

    receipt = start_receipt("windows", SOURCE_SHA, binary)
    receipt["reviewer"] = "Human reviewer"
    for gate in receipt["gates"].values():
        gate.update({"status": "passed", "evidenceFile": evidence.name,
                     "evidenceSha256": file_sha256(evidence)})

    assert validate_receipt(receipt, binary, evidence_dir) == []

    binary.write_bytes(b"different binary")
    assert any("artifact" in issue for issue in validate_receipt(receipt, binary, evidence_dir))

    binary.write_bytes(b"fake packaged binary")
    evidence.write_bytes(b"modified evidence")
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
