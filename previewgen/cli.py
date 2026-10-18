"""
PreviewGen CLI Module
Pure command-line interface for rendering and testing.
GUI-independent - no webview imports.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from previewgen.config import (
    MIN_RENDER_OUTPUT_COLORS,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_CAD_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    PreviewConfig,
)
from previewgen.renderers import generate_file


def cli_render_test(input_path: str, output_path: str | None = None, size: int | None = None) -> int:
    """
    Render a single file for testing purposes.

    Args:
        input_path: Path to input file
        output_path: Optional output path (defaults to input with .jpg extension)
        size: Optional export longest-edge in pixels (vector/procedural assets are
            re-drawn at this size; raster assets are clamped to their native pixels)

    Returns:
        0 on success, non-zero on failure
    """
    try:
        input_file = Path(input_path).resolve()
        if not input_file.is_file():
            logging.error("Input test fixture does not exist: %s", input_file)
            return 1

        out_file = Path(output_path).resolve() if output_path else input_file.with_suffix(".jpg")

        mapping: dict[str, object] = {"overwritePolicy": "overwrite"}
        if size is not None:
            mapping["outputWidth"] = size
            mapping["outputHeight"] = size
        cfg = PreviewConfig.from_mapping(mapping)
        generate_file(input_file, out_file, cfg)

        if not out_file.is_file() or out_file.stat().st_size == 0:
            logging.error("Rendered output missing or empty: %s", out_file)
            return 1

        from PIL import Image
        with Image.open(out_file) as im:
            if im.format != "JPEG" or im.width <= 0 or im.height <= 0:
                logging.error("Invalid JPEG output: format=%s, size=%s", im.format, im.size)
                return 1
            # Explicit signature check: reject anything that is not a real JPEG
            # (e.g. a placeholder/error bitmap written by a failed backend).
            if out_file.read_bytes()[:3] != b"\xff\xd8\xff":
                logging.error("Rendered output is not a valid JPEG (bad signature): %s", out_file)
                return 1
            # Reject a blank/placeholder render: the output must contain real
            # rendered content, not just one or two uniform colours.
            colors = im.convert("RGB").getcolors(maxcolors=8192)
            distinct = len(colors) if colors is not None else 8192
            if distinct < MIN_RENDER_OUTPUT_COLORS:
                logging.error(
                    "Rendered output appears blank (%d distinct colours, minimum %d): %s",
                    distinct, MIN_RENDER_OUTPUT_COLORS, out_file,
                )
                return 1
            logging.info("[RENDER-TEST-PASS] %s -> %s (%dx%d, %d bytes, %d colours)",
                        input_file.name, out_file.name, im.size[0], im.size[1],
                        out_file.stat().st_size, distinct)
        return 0
    except Exception:
        logging.exception("Render test failed for %s", input_path)
        return 1


def cli_render_test_all(
    fixture_dir: str = "tests/fixtures",
    output_dir: str | None = None,
    size: int | None = None,
) -> int:
    """
    Run render test on all fixtures in the given directory.

    Outputs are written to ``output_dir`` (a temporary directory by default) so
    that rendering never overwrites the input fixtures.
    Returns 0 if all pass, non-zero if any fail.
    """
    import tempfile

    fixtures = Path(fixture_dir).resolve()
    if not fixtures.is_dir():
        logging.error("Fixture directory does not exist: %s", fixtures)
        return 1

    test_files = sorted(
        p for p in fixtures.glob("sample.*") if p.is_file()
    )
    if not test_files:
        logging.error("No sample fixtures found in %s", fixtures)
        return 1

    logging.info("Running render test on %d fixtures", len(test_files))

    with tempfile.TemporaryDirectory(prefix="previewgen_render_test_") as tmp:
        out_root = Path(output_dir).resolve() if output_dir else Path(tmp)
        out_root.mkdir(parents=True, exist_ok=True)
        failed = 0
        for test_file in test_files:
            # Keep the full input name so distinct formats with the same stem
            # (e.g. sample.svg / sample.psd) do not collide.
            out_file = out_root / f"{test_file.name}.jpg"
            logging.info("Testing %s -> %s", test_file.name, out_file.name)
            ret = cli_render_test(str(test_file), str(out_file), size=size)
            if ret != 0:
                logging.error("FAILED: %s", test_file.name)
                failed += 1
            else:
                logging.info("PASSED: %s", test_file.name)

    if failed > 0:
        logging.error("%d of %d fixtures failed", failed, len(test_files))
        return 1
    else:
        logging.info("All %d fixtures passed!", len(test_files))
        return 0


def cli_list_formats() -> int:
    """List all supported file formats."""
    all_exts = set(SUPPORTED_EXTENSIONS) | set(SUPPORTED_3D_EXTENSIONS) | set(SUPPORTED_CAD_EXTENSIONS)
    print("Supported formats:")
    for ext in sorted(all_exts):
        is_3d = ext in SUPPORTED_3D_EXTENSIONS
        is_cad = ext in SUPPORTED_CAD_EXTENSIONS
        tags = []
        if is_3d:
            tags.append("3D")
        if is_cad:
            tags.append("CAD")
        print(f"  {ext:<8} {'[' + ', '.join(tags) + ']' if tags else ''}")
    return 0


def main_cli(args: list[str]) -> int:
    """
    Main CLI entry point.
    Supports: --render-test, --render-test-all, --list-formats
    """
    if not args:
        print("PreviewGen CLI")
        print("Usage:")
        print("  previewgen --render-test <input> [output] [--size <px>]")
        print("  previewgen --render-test-all [--fixtures <dir>] [--size <px>]")
        print("  previewgen --list-formats")
        return 0

    size: int | None = None
    if "--size" in args:
        idx = args.index("--size")
        if idx + 1 < len(args):
            try:
                size = int(args[idx + 1])
            except ValueError:
                print("ERROR: --size requires an integer pixel value", file=sys.stderr)
                return 2

    if "--render-test-all" in args:
        fixture_dir = "tests/fixtures"
        if "--fixtures" in args:
            idx = args.index("--fixtures")
            if idx + 1 < len(args):
                fixture_dir = args[idx + 1]
        return cli_render_test_all(fixture_dir, size=size)

    if "--render-test" in args:
        idx = args.index("--render-test")
        if idx + 1 >= len(args):
            print("ERROR: --render-test requires an input file argument", file=sys.stderr)
            return 2
        input_file = args[idx + 1]
        output_file = None
        if idx + 2 < len(args) and not args[idx + 2].startswith("--"):
            output_file = args[idx + 2]
        return cli_render_test(input_file, output_file, size=size)

    if "--list-formats" in args:
        return cli_list_formats()

    print(f"Unknown command: {args[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main_cli(sys.argv[1:]))
