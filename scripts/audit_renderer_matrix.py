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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        samples.append({
            "file": name, "extension": suffix,
            "mode": CAPABILITIES[suffix].mode,
            "sourceApp": str(source_app)[:100],
            "present": exists,
            "status": "not_run" if exists else "missing_fixture",
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
        before = _sha256(path)
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
            sample["status"] = "passed"
        except Exception as exc:
            sample["status"] = "failed"
            sample["failure"] = type(exc).__name__ + ": " + str(exc)[:220]
        finally:
            after = _sha256(path)
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
                        help="Require a fixture for every advertised previewable extension")
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
    if args.verify_fixtures:
        verify_samples(report, fixtures_dir, timeout=args.timeout)

    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    registry = report["registry"]
    failures = [s["file"] for s in report["samples"] if s["status"] in ("failed", "source_modified", "missing_fixture")]
    print(f"Renderer coverage: {registry['formatsWithPresentFixtures']}/{registry['advertisedPreviewFormats']} previewable extensions with fixtures")
    print(f"Absent formats: {', '.join(registry['formatsWithoutFixtures']) or '(none)'}")
    print(f"Fixture failures: {', '.join(failures) or '(none)'}")
    print(f"Audit report: {report_path}")
    if registry["advertisedWithoutCapability"] or registry["catalogWithoutAdvertisedExtension"]:
        return 1
    if args.strict and not registry["coverageComplete"]:
        return 1
    if args.verify_fixtures and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
