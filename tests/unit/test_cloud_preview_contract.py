"""Static guards for the optional root cloud-browser development entrypoint.

These are source-contract checks, not a substitute for installing and starting
the Vite server on a real preview platform.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]


def test_root_bun_workspace_has_direct_vite_scripts() -> None:
    root = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert root["private"] is True
    assert root["version"] == frontend["version"]
    for script in ("dev", "build", "test", "typecheck"):
        assert root["scripts"].get(script)
    # The root package delegates to the canonical frontend package. It must not
    # declare npm workspaces: npm would then resolve a workspace-root lock and
    # ignore frontend/package-lock.json, breaking dependency update PRs.
    assert "workspaces" not in root
    for script in ("dev", "build", "test", "typecheck"):
        assert root["scripts"][script].startswith("npm --prefix frontend ")


def test_frontend_lock_is_the_only_npm_lock() -> None:
    # npm resolves the workspace-root lock when one exists, so a second npm
    # lock would silently shadow the canonical frontend lock.
    assert not (ROOT / "package-lock.json").exists()
    assert (ROOT / "frontend/package-lock.json").is_file()


def test_cloud_bootstrap_does_not_autodetect_python_requirements() -> None:
    assert not (ROOT / "requirements.txt").exists()
    setup = (ROOT / "setup_windows.bat").read_text(encoding="utf-8")
    assert "pip install --require-hashes -r requirements-lock.txt" in setup
    for filename in ("requirements-lock.txt", "requirements-dev-lock.txt",
                     "requirements-linux-gui-lock.txt"):
        assert (ROOT / filename).is_file()


def test_dev_server_listens_on_expected_interface_without_wildcard_hosts() -> None:
    config = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'host: "0.0.0.0"' in config
    assert "port: 3000" in config
    assert "allowedHosts: true" not in config
