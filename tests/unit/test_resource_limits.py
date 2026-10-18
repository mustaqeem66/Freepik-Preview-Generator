import errno
import gzip
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen import config as previewgen_config
from previewgen import limits

pytestmark = pytest.mark.core


def test_compute_output_requirement():
    assert limits.compute_output_requirement(2400) == 2400 * 2400 * 4


def test_ensure_free_disk_space_rejects_when_insufficient(tmp_path):
    with pytest.raises(OSError) as excinfo:
        limits.ensure_free_disk_space(tmp_path, required_bytes=1 << 62)
    assert excinfo.value.errno == errno.ENOSPC


def test_ensure_free_disk_space_allows_small_requirement(tmp_path):
    limits.ensure_free_disk_space(tmp_path, required_bytes=1024)


def test_validate_raster_dimensions_rejects_oversized(tmp_path):
    path = tmp_path / "big.png"
    Image.new("RGB", (8, 8)).save(path)
    original = previewgen_config.MAX_RASTER_DIMENSION
    previewgen_config.MAX_RASTER_DIMENSION = 4
    try:
        with pytest.raises(ValueError, match="exceed"):
            limits.validate_raster_dimensions(path)
    finally:
        previewgen_config.MAX_RASTER_DIMENSION = original


def test_validate_raster_dimensions_allows_normal(tmp_path):
    path = tmp_path / "ok.png"
    Image.new("RGB", (64, 32)).save(path)
    limits.validate_raster_dimensions(path)


def test_validate_svg_limits_rejects_declared_size(tmp_path):
    path = tmp_path / "huge.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="50000" height="50000"></svg>')
    with pytest.raises(ValueError, match="declared size"):
        limits.validate_svg_limits(path)


def test_validate_svg_limits_reads_viewbox(tmp_path):
    path = tmp_path / "viewbox.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50000 50000"></svg>')
    with pytest.raises(ValueError, match="declared size"):
        limits.validate_svg_limits(path)


def test_validate_svg_limits_allows_normal(tmp_path):
    path = tmp_path / "ok.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512"></svg>')
    limits.validate_svg_limits(path)


def test_validate_svg_limits_caps_decompression(tmp_path):
    path = tmp_path / "bomb.svgz"
    payload = b'<svg xmlns="http://www.w3.org/2000/svg">' + b"<!--" + b"x" * (2 * 1024 * 1024) + b"--></svg>"
    path.write_bytes(gzip.compress(payload))
    original = previewgen_config.MAX_SVG_DECOMPRESSED_BYTES
    previewgen_config.MAX_SVG_DECOMPRESSED_BYTES = 4096
    try:
        with pytest.raises(ValueError, match="expands beyond"):
            limits.validate_svg_limits(path)
    finally:
        previewgen_config.MAX_SVG_DECOMPRESSED_BYTES = original


def test_validate_mesh_limits_rejects_oversized_obj(tmp_path):
    path = tmp_path / "tri.obj"
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\nf 1 2 3\nf 1 2 3\n")
    faces, vertices = limits.estimate_mesh_complexity(path)
    assert (faces, vertices) == (3, 3)
    original = previewgen_config.MAX_3D_FACES
    previewgen_config.MAX_3D_FACES = 2
    try:
        with pytest.raises(ValueError, match="face count"):
            limits.validate_mesh_limits(path)
    finally:
        previewgen_config.MAX_3D_FACES = original


def test_estimate_mesh_complexity_gltf(tmp_path):
    path = tmp_path / "scene.gltf"
    path.write_text(json.dumps({
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"count": 9}],
    }))
    assert limits.estimate_mesh_complexity(path) == (3, 9)


def test_estimate_mesh_complexity_ply(tmp_path):
    path = tmp_path / "shape.ply"
    path.write_text(
        "ply\nformat ascii 1.0\nelement vertex 4\nelement face 2\nend_header\n"
    )
    assert limits.estimate_mesh_complexity(path) == (2, 4)


def test_validate_loaded_mesh_rejects_oversized():
    original = previewgen_config.MAX_3D_FACES
    previewgen_config.MAX_3D_FACES = 1
    try:
        with pytest.raises(ValueError, match="face count"):
            limits.validate_loaded_mesh(SimpleNamespace(faces=[1, 2, 3], vertices=[1, 2, 3]))
    finally:
        previewgen_config.MAX_3D_FACES = original


def test_validate_loaded_mesh_allows_missing_attributes():
    limits.validate_loaded_mesh(SimpleNamespace())


def test_bounded_image_from_bytes_rejects_oversized_bytes(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (8, 8)).save(path)
    data = path.read_bytes()
    with pytest.raises(ValueError, match="embedded size"):
        limits.bounded_image_from_bytes(data, "thumb", max_bytes=4)


def test_bounded_image_from_bytes_rejects_oversized_pixels(tmp_path):
    path = tmp_path / "pixels.png"
    Image.new("RGB", (8, 8)).save(path)
    data = path.read_bytes()
    original = previewgen_config.MAX_RASTER_DIMENSION
    previewgen_config.MAX_RASTER_DIMENSION = 4
    try:
        with pytest.raises(ValueError, match="exceed"):
            limits.bounded_image_from_bytes(data, "thumb")
    finally:
        previewgen_config.MAX_RASTER_DIMENSION = original


def test_validate_source_before_parse_dispatches(tmp_path):
    png = tmp_path / "x.png"
    Image.new("RGB", (16, 16)).save(png)
    limits.validate_source_before_parse(png)

    text = tmp_path / "notes.txt"
    text.write_text("not an asset")
    limits.validate_source_before_parse(text)

    original = previewgen_config.MAX_RASTER_DIMENSION
    previewgen_config.MAX_RASTER_DIMENSION = 4
    try:
        with pytest.raises(ValueError, match="exceed"):
            limits.validate_source_before_parse(png)
    finally:
        previewgen_config.MAX_RASTER_DIMENSION = original


def test_validate_psd_limits_rejects_canvas():
    pytest.importorskip("psd_tools")
    fixture = PROJECT_ROOT / "tests" / "fixtures" / "sample.psd"
    if not fixture.is_file():
        pytest.skip("sample.psd fixture missing")
    original = previewgen_config.MAX_PSD_DIMENSION
    previewgen_config.MAX_PSD_DIMENSION = 1
    try:
        with pytest.raises(ValueError, match="canvas"):
            limits.validate_psd_limits(fixture)
    finally:
        previewgen_config.MAX_PSD_DIMENSION = original


def test_validate_dxf_entity_limits_rejects(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (1, 1))
    msp.add_circle((0, 0), 1)
    original = previewgen_config.MAX_CAD_ENTITIES
    previewgen_config.MAX_CAD_ENTITIES = 1
    try:
        with pytest.raises(ValueError, match="entity count"):
            limits.validate_dxf_entity_limits(doc)
    finally:
        previewgen_config.MAX_CAD_ENTITIES = original

def test_validate_dxf_entity_limits_fails_closed_on_uninspectable_document():
    """If modelspace cannot be inspected, fail closed with ResourceInspectionError."""
    class BrokenDoc:
        def modelspace(self):
            raise RuntimeError("Corrupt modelspace section")

    with pytest.raises(limits.ResourceInspectionError, match="Failed to inspect DXF"):
        limits.validate_dxf_entity_limits(BrokenDoc())


def test_extract_zip_member_bounded_copies_member(tmp_path):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("entry.bin", b"hello world")
    dest = tmp_path / "out.bin"
    with zipfile.ZipFile(archive, "r") as zf:
        limits.extract_zip_member_bounded(zf, "entry.bin", dest)
    assert dest.read_bytes() == b"hello world"


def test_extract_zip_member_bounded_rejects_oversized_member(tmp_path):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("big.bin", b"x" * 4096)
    dest = tmp_path / "out.bin"
    original = previewgen_config.MAX_MEMBER_BYTES
    previewgen_config.MAX_MEMBER_BYTES = 1024
    try:
        with zipfile.ZipFile(archive, "r") as zf, pytest.raises(ValueError, match="member size"):
            limits.extract_zip_member_bounded(zf, "big.bin", dest)
    finally:
        previewgen_config.MAX_MEMBER_BYTES = original


def test_extract_zip_member_bounded_rejects_compression_ratio(tmp_path):
    import zipfile

    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.bin", b"\x00" * (1024 * 1024))
    dest = tmp_path / "out.bin"
    original = previewgen_config.MAX_COMPRESSION_RATIO
    previewgen_config.MAX_COMPRESSION_RATIO = 2
    try:
        with zipfile.ZipFile(archive, "r") as zf, pytest.raises(ValueError, match="compression ratio"):
            limits.extract_zip_member_bounded(zf, "bomb.bin", dest)
    finally:
        previewgen_config.MAX_COMPRESSION_RATIO = original

