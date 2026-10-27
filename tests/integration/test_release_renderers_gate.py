"""
Release Gate: multi-format renderer verification.

This gate has two responsibilities:

1. Guarantee that every mandatory renderer engine is installed and importable.
2. Render tiny deterministic fixtures for each declared format through either
   the packaged artifact (when available) or the in-process CLI, then validate
   that the JPEG output is real content produced by the real renderer.

Set ``PREVIEWGEN_BINARY`` to point at a frozen executable to exercise the
packaged artifact explicitly; otherwise a *fresh* ``dist/PreviewGen/PreviewGen``
(newer than the Python sources) is auto-detected. When no valid artifact is
available the in-process CLI is used so the renderer engines are still covered.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.config import CHECKER_DARK, CHECKER_LIGHT

FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"

# fixture file -> (mandatory engine module, minimum expected dimension, label)
FIXTURE_MATRIX = {
    "sample.png": ("PIL", 256, "PNG"),
    "sample.jpg": ("PIL", 256, "RASTER"),
    "sample.svg": ("resvg_py", 200, "SVG"),
    "sample.psd": ("psd_tools", 160, "PSD"),
    "sample.dxf": ("ezdxf", 64, "DXF"),
    "sample.obj": ("trimesh", 256, "OBJ"),
    "sample.glb": ("trimesh", 256, "GLB"),
    "sample.3mf": ("trimesh", 256, "3MF"),
    "sample_pbr.glb": ("trimesh", 256, "PBR"),
    "sample.step": ("cascadio", 256, "STEP"),
    "sample.igs": ("cascadio", 256, "IGES"),
    "sample.dae": ("collada", 64, "COLLADA"),
}


MANDATORY_RENDERER_ENGINES = [
    "PIL",
    "resvg_py",
    "psd_tools",
    "trimesh",
    "ezdxf",
    "cascadio",
    "matplotlib",
    "fontTools",
    "collada",
    "lxml",
    "networkx",
]

# Mandatory engines pulled in transitively by the renderer stack (e.g. text and
# composition, or trimesh's 3MF loader) rather than owning a format-specific
# fixture of their own.
SUPPORTING_RENDERER_ENGINES = {"matplotlib", "fontTools", "lxml", "networkx"}


@pytest.mark.core
def test_release_matrix_exercises_every_mandatory_engine():
    """A signed artifact is only releasable when every mandatory engine is
    exercised by the fixture matrix rendered through the frozen executable."""
    matrix_engines = {engine for engine, _dim, _label in FIXTURE_MATRIX.values()}
    mandatory = set(MANDATORY_RENDERER_ENGINES)

    # No fixture may depend on an engine that is not declared mandatory.
    assert matrix_engines <= mandatory, f"undeclared fixture engines: {matrix_engines - mandatory}"
    # Every mandatory engine must be covered, except the declared supporting set.
    uncovered = mandatory - matrix_engines
    assert uncovered <= SUPPORTING_RENDERER_ENGINES, f"mandatory engines without a fixture: {uncovered}"

    labels = {label for _engine, _dim, label in FIXTURE_MATRIX.values()}
    assert {
        "PNG", "RASTER", "SVG", "PSD", "DXF", "OBJ", "GLB", "3MF", "PBR",
        "STEP", "IGES", "COLLADA",
    } == labels
    assert all(dim > 0 for _engine, dim, _label in FIXTURE_MATRIX.values())


@pytest.mark.full_runtime
def test_release_all_mandatory_renderers_importable():
    import importlib

    missing = []
    for module in MANDATORY_RENDERER_ENGINES:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            missing.append(f"{module} ({exc})")

    assert not missing, (
        "Mandatory release renderer engines are not importable: "
        + ", ".join(missing)
        + ". Install the full runtime dependencies with: pip install -r requirements.txt"
    )

@pytest.mark.full_runtime
def test_release_fixtures_present():
    missing = [name for name in FIXTURE_MATRIX if not (FIXTURES_DIR / name).is_file()]
    assert not missing, f"Missing render fixtures: {missing}"


def _newest_source_mtime() -> float:
    paths = [
        PROJECT_ROOT / "app.py",
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / "processor.py",
    ]
    package = PROJECT_ROOT / "previewgen"
    if package.is_dir():
        paths.extend(package.rglob("*.py"))
    return max((p.stat().st_mtime for p in paths if p.is_file()), default=0.0)


def _artifact_path():
    """
    Locate a frozen artifact to exercise.

    ``PREVIEWGEN_BINARY`` takes precedence (the release/clean-machine gate sets
    it). Otherwise ``dist/PreviewGen/PreviewGen[.exe]`` is used only when it is
    newer than the Python sources, so a stale pre-refactor bundle is never
    mistaken for a valid release artifact.
    """
    env = os.environ.get("PREVIEWGEN_BINARY")
    if env:
        candidate = Path(env)
        assert candidate.is_file(), f"PREVIEWGEN_BINARY does not exist: {candidate}"
        return candidate

    newest_source = _newest_source_mtime()
    for cand in (
        PROJECT_ROOT / "dist" / "PreviewGen" / "PreviewGen",
        PROJECT_ROOT / "dist" / "PreviewGen" / "PreviewGen.exe",
        PROJECT_ROOT / "dist" / "PreviewGen.app" / "Contents" / "MacOS" / "PreviewGen",
    ):
        if cand.is_file() and cand.stat().st_mtime >= newest_source:
            return cand
    return None


def _run_render(input_path: Path, output_path: Path, size: int | None = None) -> int:
    exe = _artifact_path()
    if exe is not None:
        cmd = [str(exe), "--render-test", str(input_path), str(output_path)]
        if size is not None:
            cmd += ["--size", str(size)]
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
        return proc.returncode
    from previewgen.cli import cli_render_test
    return cli_render_test(str(input_path), str(output_path), size=size)


# Colors the renderer composites behind transparent assets; a real render of a
# populated fixture must cover clearly more than these placeholder pixels.
BACKGROUND_RGB = {CHECKER_LIGHT[:3], CHECKER_DARK[:3]}
MIN_NON_BACKGROUND_FRACTION = 0.05


def _non_background_fraction(im: Image.Image, sample: int = 256) -> float:
    small = im.convert("RGB").resize((sample, sample), Image.NEAREST)
    counts = small.getcolors(maxcolors=sample * sample) or []
    total = sample * sample
    background = sum(count for count, color in counts if tuple(color) in BACKGROUND_RGB)
    return (total - background) / total


def _fixture_snapshot() -> dict[str, int]:
    return {p.name: p.stat().st_size for p in FIXTURES_DIR.iterdir()}


@pytest.mark.full_runtime
@pytest.mark.parametrize("fixture_name", sorted(FIXTURE_MATRIX))
def test_release_fixture_renders_to_valid_content(fixture_name):
    engine_module, min_dim, label = FIXTURE_MATRIX[fixture_name]
    if engine_module != "PIL":
        pytest.importorskip(engine_module)
    src = FIXTURES_DIR / fixture_name
    assert src.is_file(), f"Fixture missing: {src}"

    before = _fixture_snapshot()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"{label.lower()}-output.jpg"
        exit_code = _run_render(src, out)

        assert exit_code == 0, f"{label}: render-test exited {exit_code}"
        assert out.is_file(), f"{label}: output not created"
        assert out.stat().st_size > 0, f"{label}: output is empty"

        # Valid JPEG signature (FFD8FF).
        with open(out, "rb") as fh:
            assert fh.read(3) == b"\xff\xd8\xff", f"{label}: invalid JPEG signature"

        with Image.open(out) as im:
            assert im.format == "JPEG", f"{label}: unexpected format {im.format}"
            width, height = im.size
            assert width >= min_dim and height >= min_dim, (
                f"{label}: unexpected dimensions {im.size} (min {min_dim})"
            )

            # Output contains real rendered content, not a blank/placeholder image.
            colors = im.convert("RGB").getcolors(maxcolors=8192)
            distinct = len(colors) if colors is not None else 8192
            assert distinct >= 8, f"{label}: output appears blank ({distinct} colors)"

            # The render must cover actual geometry, not just the transparency
            # checkerboard or a solid blank frame.
            fraction = _non_background_fraction(im)
            assert fraction >= MIN_NON_BACKGROUND_FRACTION, (
                f"{label}: output is background only ({fraction:.3f} non-background pixels)"
            )

    # Rendering is read-only: it must never mutate the fixture inputs.
    assert _fixture_snapshot() == before, f"{label}: render modified the fixtures directory"

@pytest.mark.full_runtime
def test_release_vector_respects_requested_export_size():
    """A vector asset is re-drawn at the requested export size end-to-end."""
    pytest.importorskip("resvg_py")
    src = FIXTURES_DIR / "sample.svg"
    assert src.is_file(), f"Fixture missing: {src}"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "vector-sized.jpg"
        exit_code = _run_render(src, out, size=512)
        assert exit_code == 0, f"render-test exited {exit_code}"
        with Image.open(out) as im:
            assert im.format == "JPEG"
            assert max(im.size) == 512, f"expected longest edge 512, got {im.size}"


@pytest.mark.full_runtime
def test_release_raster_clamps_to_native_size():
    """A raster asset is never enlarged beyond its native pixels."""
    src = FIXTURES_DIR / "sample.png"
    assert src.is_file(), f"Fixture missing: {src}"
    with Image.open(src) as native:
        native_longest = max(native.size)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "raster-sized.jpg"
        exit_code = _run_render(src, out, size=native_longest * 4)
        assert exit_code == 0, f"render-test exited {exit_code}"
        with Image.open(out) as im:
            assert max(im.size) <= native_longest, f"raster upscaled: {im.size} > {native_longest}"


@pytest.mark.packaged_release
def test_release_frozen_artifact_is_exercised_when_supplied():
    """
    Packaged-release gate: when ``PREVIEWGEN_BINARY`` is set (the release /
    clean-machine gate) the *frozen* executable must render all fixtures. Source
    imports prove nothing about the packaged build — PyInstaller can omit native
    libraries, plugins, fonts, or renderer backends while still building.
    """
    env = os.environ.get("PREVIEWGEN_BINARY", "").strip()
    is_release_gate = os.environ.get("PREVIEWGEN_RELEASE_GATE") == "1"
    if not env:
        if is_release_gate:
            pytest.fail("FATAL: PREVIEWGEN_BINARY must be set and non-empty in the packaged-release gate!")
        pytest.skip("PREVIEWGEN_BINARY not set; pass PREVIEWGEN_BINARY to test frozen artifact")

    candidate = Path(env)
    if not candidate.is_file():
        pytest.fail(f"FATAL: PREVIEWGEN_BINARY target does not exist or is not a file: {candidate}")
    exe = candidate

    for fixture_name, (_engine_module, min_dim, label) in sorted(FIXTURE_MATRIX.items()):
        src = FIXTURES_DIR / fixture_name
        assert src.is_file(), f"Fixture missing: {src}"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"frozen-{label.lower()}.jpg"
            proc = subprocess.run(
                [str(exe), "--render-test", str(src), str(out)],
                capture_output=True,
                timeout=300,
            )
            assert proc.returncode == 0, (
                f"frozen artifact failed to render {label} ({src.name}, exit {proc.returncode}): "
                f"{proc.stderr.decode(errors='replace')[-500:]}"
            )
            assert out.is_file() and out.stat().st_size > 0, f"frozen artifact produced empty output for {label}"
            with open(out, "rb") as fh:
                assert fh.read(3) == b"\xff\xd8\xff", f"{label}: invalid JPEG signature"
            with Image.open(out) as im:
                assert im.format == "JPEG", f"{label}: unexpected format {im.format}"
                assert im.width >= min_dim and im.height >= min_dim, f"{label}: unexpected dimensions {im.size}"
                colors = im.convert("RGB").getcolors(maxcolors=8192)
                distinct = len(colors) if colors is not None else 8192
                assert distinct >= 8, f"frozen output for {label} appears blank"
                fraction = _non_background_fraction(im)
                assert fraction >= MIN_NON_BACKGROUND_FRACTION, (
                    f"frozen output for {label} is background only ({fraction:.3f} non-background pixels)"
                )
