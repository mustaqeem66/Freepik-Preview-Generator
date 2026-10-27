#!/usr/bin/env python3
"""Local-only native acceptance receipt, never a self-certified release.

Examples:
 python scripts/native_release_evidence.py init --platform windows --commit <40-hex> \\
   --artifact path/to/installer.exe --output local-native/windows.json
 python scripts/native_release_evidence.py verify --receipt local-native/windows.json \\
   --artifact path/to/installer.exe --evidence-dir local-native/evidence
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Gate names are deliberately specific and stable: a reviewer must test every
# scenario in the packaged native app. They are not automatically "passed" by
# authoring source tests or by a green GitHub mergeability indicator.
COMMON_GATES: tuple[str, ...] = (
    "native_file_picker_and_exact_read_grants",
    "blocked_unselected_siblings_symlinks_and_zip_members",
    "export_destination_authorization_and_source_integrity",
    "preview_zip_3d_cad_creator_formats_and_cancellation",
    "three_files_two_directories_batch_and_report",
    "native_webview_bridge_and_external_origin_csp_block",
    "independent_renderer_oracles_and_dependency_packaging",
    "light_dark_accessibility_and_keyboard_focus",
)
PLATFORM_GATES: dict[str, tuple[str, ...]] = {
    "windows": (
        "portable_exe_startup_and_exit",
        "installed_setup_upgrade_repair_and_uninstall",
        "idle_300_seconds_and_freeze_diagnostic",
        "dpi_100_125_150_200_and_webview2_runtime",
        "windows_authenticode_signature_verified_for_release",
    ),
    "linux": (
        "appimage_startup_and_exit",
        "native_webkit_gtk_sandbox_and_gpu_fallback",
        "appimage_checksum_dependency_and_distribution_qa",
    ),
    "macos": (
        "dmg_install_app_startup_and_exit",
        "native_cocoa_dialog_webview_and_arch_compatibility",
        "codesign_notarization_and_gatekeeper_validation",
    ),
}
SHA40 = re.compile(r"^[a-fA-F0-9]{40}$")
SHA64 = re.compile(r"^[a-fA-F0-9]{64}$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def required_gates(platform: str) -> tuple[str, ...]:
    if platform not in PLATFORM_GATES:
        raise ValueError(f"Unsupported platform: {platform!r}")
    return COMMON_GATES + PLATFORM_GATES[platform]


def start_receipt(platform: str, commit: str, artifact: Path) -> dict[str, Any]:
    if not SHA40.fullmatch(commit):
        raise ValueError("Commit must be an exact 40-character Git SHA")
    if not artifact.is_file():
        raise ValueError("Packaged artifact must be an existing file")
    if not artifact.name or artifact.name.startswith("."):
        raise ValueError("Packaged artifact must have a display-safe basename")
    return {
        "schemaVersion": 1,
        "scope": "Local native packaged-app acceptance; no automatic signoff",
        "platform": platform,
        "sourceCommit": commit.lower(),
        "artifact": {"name": artifact.name, "sha256": file_sha256(artifact)},
        "reviewer": "",
        "gates": {
            name: {"status": "pending", "evidenceFile": "", "evidenceSha256": "", "notes": ""}
            for name in required_gates(platform)
        },
    }


def validate_receipt(receipt: dict[str, Any], artifact: Path, evidence_dir: Path) -> list[str]:
    """Return *all* release blocking reasons; do not mutate source or receipt."""
    failures: list[str] = []
    if receipt.get("schemaVersion") != 1:
        failures.append("Unsupported or absent receipt schema version")
    if not SHA40.fullmatch(str(receipt.get("sourceCommit", ""))):
        failures.append("Missing/invalid exact source commit")
    platform = receipt.get("platform", "")
    try:
        required = set(required_gates(platform))
    except ValueError as exc:
        return failures + [str(exc)]
    if not isinstance(receipt.get("reviewer"), str) or not receipt["reviewer"].strip():
        failures.append("Human native QA reviewer has not signed the receipt")
    # An unsigned developer build can be useful for smoke tests, but it must
    # NEVER be represented as a signed release acceptance receipt. The exact
    # Windows Authenticode (or macOS codesign/notarization) gate must have
    # independently checked evidence before a complete receipt can pass.
    record = receipt.get("artifact")
    if not isinstance(record, dict):
        failures.append("Missing packaged binary metadata")
    elif (
        record.get("name") != artifact.name
        or not SHA64.fullmatch(str(record.get("sha256", "")))
    ):
        failures.append("Packaged artifact basename or SHA-256 is invalid")
    elif not artifact.is_file() or file_sha256(artifact) != record["sha256"].lower():
        failures.append("Actual packaged artifact does not match the recorded SHA-256")
    gates = receipt.get("gates")
    if not isinstance(gates, dict):
        return failures + ["Missing structured gate results"]
    for missing in sorted(required - set(gates)):
        failures.append(f"Missing gate: {missing}")
    for extra in sorted(set(gates) - required):
        failures.append(f"Unexpected gate: {extra}")
    for name in sorted(required & set(gates)):
        record = gates[name]
        if not isinstance(record, dict) or record.get("status") != "passed":
            failures.append(f"{name}: not passed")
            continue
        evidence = record.get("evidenceFile")
        digest = record.get("evidenceSha256")
        if not isinstance(evidence, str) or not evidence or evidence.startswith(".") or Path(evidence).name != evidence or "/" in evidence or "\\" in evidence:
            failures.append(f"{name}: evidence filename must be a safe basename")
            continue
        if not isinstance(digest, str) or not SHA64.fullmatch(digest):
            failures.append(f"{name}: missing SHA-256 of independent evidence")
            continue
        path = evidence_dir / evidence
        if not path.is_file() or file_sha256(path) != digest.lower():
            failures.append(f"{name}: evidence missing or digest mismatch")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a pending, unapproved native QA receipt")
    init.add_argument("--platform", choices=sorted(PLATFORM_GATES), required=True)
    init.add_argument("--commit", required=True)
    init.add_argument("--artifact", type=Path, required=True)
    init.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify", help="Fail unless every native QA check has evidence")
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--artifact", type=Path, required=True)
    verify.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            receipt = start_receipt(args.platform, args.commit, args.artifact)
            if args.output.exists():
                raise ValueError("Refusing to overwrite an existing native QA receipt")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
            print(f"PENDING: created {args.output} with {len(receipt['gates'])} unverified gates")
            return 0
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict):
            raise ValueError("Receipt must be a JSON object")
        failures = validate_receipt(receipt, args.artifact, args.evidence_dir)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    if failures:
        for reason in failures:
            print(f"FAIL: {reason}")
        return 1
    print("PASS: all recorded native acceptance gates have matching evidence and artifact digest")
    print("NOTE: Review credibility and independent renderer fidelity still require human evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
