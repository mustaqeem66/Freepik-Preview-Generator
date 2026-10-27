"""Regression checks for bounded mesh preflight reads before heavy decoders."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from previewgen import limits

pytestmark = pytest.mark.core


@pytest.mark.parametrize("suffix, data", [
    (".obj", b"v " + b"9" * 100 + b"\\n"),
    (".stl", b"solid test\\nfacet " + b"9" * 100 + b"\\n"),
    (".ply", b"ply\\n" + b"comment " + b"9" * 100 + b"\\nend_header\\n"),
])
def test_mesh_preparse_refuses_oversize_single_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, data: bytes
) -> None:
    monkeypatch.setattr(limits, "MAX_MESH_INSPECTION_LINE_BYTES", 64)
    path = tmp_path / ("bad" + suffix)
    path.write_bytes(data.replace(b"\\n", b"\n"))
    with pytest.raises(ValueError, match="line exceeds"):
        limits.estimate_mesh_complexity(path)


def test_mesh_inspection_still_counts_normal_obj_stl_and_ply(tmp_path: Path):
    obj = tmp_path / "normal.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    assert limits.estimate_mesh_complexity(obj) == (1, 3)

    stl = tmp_path / "normal.stl"
    stl.write_text(
        "solid sample\nfacet normal 0 0 1\nouter loop\n"
        "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
        "endloop\nendfacet\nendsolid sample\n"
    )
    assert limits.estimate_mesh_complexity(stl) == (1, 3)

    ply = tmp_path / "normal.ply"
    ply.write_text(
        "ply\nformat ascii 1.0\nelement vertex 4\nelement face 2\nend_header\n"
    )
    assert limits.estimate_mesh_complexity(ply) == (2, 4)


def _glb_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack("<I4s", len(payload), kind) + payload


def _glb(*chunks: bytes) -> bytes:
    body = b"".join(chunks)
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def test_glb_non_json_binary_chunk_is_skipped_without_parsing(tmp_path: Path):
    document = json.dumps({"accessors": [{"count": 9}], "meshes": [
        {"primitives": [{"indices": 0}]}]}).encode("utf-8")
    source = tmp_path / "binary_then_json.glb"
    source.write_bytes(_glb(_glb_chunk(b"BIN\x00", b"x" * 4096),
                            _glb_chunk(b"JSON", document)))
    assert limits.estimate_mesh_complexity(source) == (3, 0)


def test_glb_oversized_json_denied_before_loading_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(limits, "MAX_MESH_INSPECTION_JSON_BYTES", 128)
    source = tmp_path / "oversized.glb"
    payload = b" " * 256
    source.write_bytes(_glb(_glb_chunk(b"JSON", payload)))
    with pytest.raises(ValueError, match="JSON chunk exceeds"):
        limits.estimate_mesh_complexity(source)


def test_glb_declared_chunk_overrunning_file_rejected(tmp_path: Path):
    source = tmp_path / "truncated.glb"
    source.write_bytes(struct.pack("<4sII", b"glTF", 2, 1024) +
                       struct.pack("<I4s", 4096, b"BIN\x00") + b"x" * 8)
    with pytest.raises(ValueError, match="actual file size"):
        limits.estimate_mesh_complexity(source)


def test_gltf_json_over_limit_denied_before_full_json_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(limits, "MAX_MESH_INSPECTION_JSON_BYTES", 120)
    source = tmp_path / "huge.gltf"
    source.write_bytes(b" " * 121)
    with pytest.raises(ValueError, match="JSON document exceeds"):
        limits.estimate_mesh_complexity(source)


def test_small_gltf_json_still_counts_geometry(tmp_path: Path):
    source = tmp_path / "sample.gltf"
    source.write_text(json.dumps({"accessors": [{"count": 12}],
                                  "meshes": [{"primitives": [{"indices": 0}]}]}))
    assert limits.estimate_mesh_complexity(source) == (4, 0)
