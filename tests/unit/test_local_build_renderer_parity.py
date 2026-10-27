"""The local Windows installer and release environment gate must agree with CI."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.core


def _literal_assignment(file: Path, name: str):
    tree = ast.parse(file.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"Missing {name} in {file}")


def test_environment_verifier_agrees_with_mandatory_release_engines():
    expected = set(_literal_assignment(
        ROOT / "tests/integration/test_release_renderers_gate.py",
        "MANDATORY_RENDERER_ENGINES",
    ))
    actual = set(_literal_assignment(ROOT / "scripts/verify_environment.py", "MANDATORY_ENGINES"))
    assert actual == expected, f"Missing: {expected - actual}; unexpected: {actual - expected}"
    assert "fontTools" in actual


def test_local_windows_packaging_collects_3d_scene_parsers():
    script = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
    for module in ("collada", "lxml", "networkx", "fontTools"):
        assert f"--collect-all {module}" in script
        assert f"--collect-all {module}" in workflow
