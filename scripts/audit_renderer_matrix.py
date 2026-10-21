#!/usr/bin/env python3
"""Auditable renderer-format coverage without inventing proprietary fixtures.

Default: inventory catalog and supplied fixture manifest; does not execute
expensive decoders. Add --verify-fixtures for isolated real renders and
--strict to fail for every advertised previewable format without a fixture.

Example:
 python scripts/audit_renderer_matrix.py --verify-fixtures
 python scripts/audit_renderer_matrix.py --verify-fixtures --strict
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from previewgen.renderers.capabilities import CAPABILITIES, validate_registry

DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "renderer-samples.json"
DEFAULT_REPORT = ROOT / "renderer-matrix-local.json"
MAX_ORACLE_MEAN_ERROR = 32.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()



def _validated_oracle(item: dict[str, Any], fixtures_dir: Path) -> dict[str, Any] | None:
    """Accept only explicit, independently reviewed local reference images.

    No implicit oracle is generated from a renderer output: doing so would
    certify the implementation against itself and conceal wrong geometry.
    """
    raw = item.get("oracle")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("oracle must be an object")
    image = raw.get("image")
    checksum = raw.get("sha256")
    reviewer = raw.get("reviewedBy")
    maximum = raw.get("maxMeanAbsoluteError")
    version = item.get("sourceVersion")
    if (not isinstance(image, str) or not image
            or Path(image).name != image or "/" in image or "\\" in image
            or image.startswith(".") or Path(image).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp")):
        raise ValueError("oracle.image must be a local image basename")
    if (not isinstance(checksum, str) or len(checksum) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in checksum)):
        raise ValueError("oracle.sha256 must be a full SHA-256 digest")
    if not isinstance(maximum, (float, int)) or isinstance(maximum, bool) or not 0 <= maximum <= MAX_ORACLE_MEAN_ERROR:
        raise ValueError("oracle.maxMeanAbsoluteError must be between 0 and 32")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
        raise ValueError("oracle.reviewedBy must identify a human reviewer")
    if not isinstance(version, str) or not version.strip() or len(version) > 100:
        raise ValueError("sourceVersion is required when an oracle is supplied")
    target = (fixtures_dir / image).resolve()
    if target.parent != fixtures_dir.resolve():
        raise ValueError("Oracle image escaped the fixture directory")
    return {
        "image": image,
        "sha256": checksum.lower(),
        "reviewedBy": reviewer,
        "maxMeanAbsoluteError": float(maximum),
    }


def _compare_to_oracle(output: Any, oracle: dict[str, Any], fixtures_dir: Path) -> float:
    """Measure RGB mean absolute error against a trusted same-size reference."""
    from PIL import Image, ImageChops, ImageStat

    approved = fixtures_dir / oracle["image"]
    if not approved.is_file():
        raise ValueError("Approved oracle image is missing")
    if _sha256(approved).lower() != oracle["sha256"]:
        raise ValueError("Approved oracle SHA-256 does not match its manifest")
    with Image.open(approved) as reference:
        if reference.width * reference.height > 16_000_000:
            raise ValueError("Oracle image exceeds the 16-million-pixel audit bound")
        reference.load()
        if reference.size != output.size:
            raise ValueError(
                f"Oracle size {reference.size} differs from rendered output {output.size}"
            )
        size = (96, 96)
        actual = output.convert("RGB").resize(size, Image.Resampling.BILINEAR)
        expected = reference.convert("RGB").resize(size, Image.Resampling.BILINEAR)
        difference = ImageChops.difference(actual, expected)
        mean_error = sum(ImageStat.Stat(difference).mean) / 3
        if mean_error > oracle["maxMeanAbsoluteError"]:
            raise ValueError(
                f"Fidelity error {mean_error:.2f} exceeds approved limit "
                f"{oracle['maxMeanAbsoluteError']:.2f}"
            )
        return round(mean_error, 3)

def inspect_inventory(manifest: dict[str, Any], fixtures_dir: Path) -> dict[str, Any]:
    missing, unexpected = validate_registry()
    entries = manifest.get("samples")
    if not isinstance(entries, list):
        raise ValueError("Manifest must contain a samples array")
    samples: list[dict[str, Any]] = []
    covered: set[str] = set()
    seen_names: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Each sample must be an object")
        name = item.get("file")
        source_app = item.get("sourceApp", "unknown")
        if not isinstance(name, str) or not name or name in seen_names:
            raise ValueError("Invalid or duplicate sample filename")
        # Do not accept path traversal in an externally supplied manifest.
        if Path(name).name != name or name.startswith("."):
            raise ValueError(f"Sample must be a single basename: {name}")
        seen_names.add(name)
        suffix = Path(name).suffix.lower()
        if suffix not in CAPABILITIES or suffix == ".zip":
            raise ValueError(f"Unrecognized or container-only sample type: {name}")
        path = (fixtures_dir / name).resolve()
        if path.parent != fixtures_dir.resolve():
            raise ValueError("Sample path escaped the fixtures directory")
        exists = path.is_file()
        if exists:
            covered.add(suffix)
        oracle = _validated_oracle(item, fixtures_dir)
        samples.append({
            "file": name, "extension": suffix,
            "mode": CAPABILITIES[suffix].mode,
            "sourceApp": str(source_app)[:100],
            "sourceVersion": str(item.get("sourceVersion") or "")[:100],
            "present": exists,
            "status": "not_run" if exists else "missing_fixture",
            "oracle": oracle,
            "oracleStatus": "not_run" if oracle is not None else "not_provided",
            "fidelityVerified": False,
        })

    preview_extensions = set(CAPABILITIES) - {".zip"}
    untested = sorted(preview_extensions - covered)
    return {
        "schemaVersion": 1,
        "capturedUtc": datetime.now(UTC).isoformat(),
        "registry": {
            "advertisedWithoutCapability": sorted(missing),
            "catalogWithoutAdvertisedExtension": sorted(unexpected),
            "advertisedPreviewFormats": len(preview_extensions),
            "formatsWithPresentFixtures": len(covered),
            "formatsWithoutFixtures": untested,
            "coverageComplete": not untested and not missing and not unexpected,
        },
        "formats": {
            ext: cap.public() for ext, cap in sorted(CAPABILITIES.items())
        },
        "samples": samples,
        "runMode": "inventory",
    }


def verify_samples(report: dict[str, Any], fixtures_dir: Path, timeout: float) -> None:
    """Run actual isolated renderer workers, never reuse or rewrite a source."""
    from PIL import Image

    from previewgen.config import PreviewConfig
    from previewgen.renderer_process import render_file_isolated

    report["runMode"] = "isolated_render"
    for sample in report["samples"]:
        if not sample["present"]:
            continue
        path = (fixtures_dir / sample["file"]).resolve()
        try:
            before = _sha256(path)
        except OSError as exc:
            sample["status"] = "missing_fixture"
            sample["present"] = False
            sample["sourcePreserved"] = False
            sample["failure"] = f"Source unavailable before rendering: {type(exc).__name__}"
            continue
        sample["sourceSha256"] = before
        try:
            with tempfile.TemporaryDirectory(prefix="previewgen_matrix_") as temp:
                out = Path(temp) / "preview.jpg"
                render_file_isolated(
                    path, out, PreviewConfig(text=""), timeout_seconds=timeout
                )
                with Image.open(out) as image:
                    image.load()
                    if image.format != "JPEG" or not min(image.size) > 0:
                        raise ValueError("Renderer did not create a valid JPEG")
                    # A solid color or a single checkerboard pixel alone must
                    # never be reported as a valid illustrated preview.
                    palette = image.convert("RGB").resize((96, 96)).getcolors(96 * 96)
                    distinct = len(palette) if palette is not None else 96 * 96
                    if distinct < 8:
                        raise ValueError(f"Output has only {distinct} distinct colors")
                    sample["outputSize"] = list(image.size)
                    sample["distinctColors"] = distinct
                    oracle = sample["oracle"]
                    if oracle is not None:
                        sample["oracleMeanAbsoluteError"] = _compare_to_oracle(
                            image, oracle, fixtures_dir
                        )
                        sample["oracleStatus"] = "matched"
                        sample["fidelityVerified"] = True
            sample["status"] = "passed"
        except Exception as exc:
            sample["status"] = "failed"
            if sample["oracle"] is not None:
                sample["oracleStatus"] = "failed"
            sample["failure"] = type(exc).__name__ + ": " + str(exc)[:220]
        finally:
            # A renderer may delete/truncate a file before failing. Preserve
            # the evidence instead of crashing the entire audit report.
            try:
                after = _sha256(path)
            except OSError as exc:
                sample["sourcePreserved"] = False
                sample["sourceIntegrityError"] = type(exc).__name__
            else:
                sample["sourcePreserved"] = before == after
            if not sample["sourcePreserved"]:
                sample["status"] = "source_modified"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixtures-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--verify-fixtures", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="Require all formats, successful isolated renders and reviewed matching visual oracles")
    parser.add_argument("--require-oracles", action="store_true",
                        help="Require approved matching visual oracle for every present fixture")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    if not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    fixtures_dir = args.fixtures_dir or args.manifest.parent
    try:
        report = inspect_inventory(manifest, fixtures_dir)
    except ValueError as exc:
        parser.error(str(exc))
    # "Strict" must be a true evidence gate, never a fixture-count-only
    # shortcut that passes without running any renderer.
    if args.verify_fixtures or args.strict or args.require_oracles:
        verify_samples(report, fixtures_dir, timeout=args.timeout)

    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    registry = report["registry"]
    failures = [s["file"] for s in report["samples"] if s["status"] in ("failed", "source_modified", "missing_fixture")]
    uncertified = [s["file"] for s in report["samples"] if s["present"] and not s["fidelityVerified"]]
    report["registry"]["oracleVerifiedFixtures"] = sum(
        sample["fidelityVerified"] for sample in report["samples"]
    )
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "Renderer coverage: "
        f"{registry['formatsWithPresentFixtures']}/{registry['advertisedPreviewFormats']} "
        "previewable extensions with fixtures"
    )
    print(f"Absent formats: {', '.join(registry['formatsWithoutFixtures']) or '(none)'}")
    print(f"Fixture failures: {', '.join(failures) or '(none)'}")
    print(f"Unverified image fidelity: {', '.join(uncertified) or '(none)'}")
    print(f"Audit report: {report_path}")
    if registry["advertisedWithoutCapability"] or registry["catalogWithoutAdvertisedExtension"]:
        return 1
    if args.strict and not registry["coverageComplete"]:
        return 1
    if (args.verify_fixtures or args.strict or args.require_oracles) and failures:
        return 1
    if (args.strict or args.require_oracles) and (
        uncertified or not report["samples"] or registry["oracleVerifiedFixtures"] == 0
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
