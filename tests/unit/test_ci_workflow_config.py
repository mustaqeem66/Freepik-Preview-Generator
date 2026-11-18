"""Structural guards for the CI workflow and Dependabot configuration.

These checks catch configuration shapes that parse as YAML but behave in a way
the repository does not intend: duplicate mapping keys, an advisory gate that
skips a lock, or a Dependabot ecosystem whose limit contradicts its comment.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = (
    ROOT / ".github/workflows/build.yml",
    ROOT / ".github/workflows/pr-checks.yml",
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """A SafeLoader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ValueError(f"duplicate key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _load_unique(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_has_no_duplicate_yaml_keys(workflow: Path) -> None:
    # A duplicate key is silently resolved by most YAML loaders, so GitHub may
    # see a different configuration than the file appears to describe.
    _load_unique(workflow)


def test_dependabot_config_has_no_duplicate_yaml_keys() -> None:
    _load_unique(ROOT / ".github/dependabot.yml")


def test_dependabot_pip_updates_are_disabled_with_one_limit() -> None:
    config = _load_unique(ROOT / ".github/dependabot.yml")
    pip_entries = [
        entry for entry in config["updates"]
        if entry["package-ecosystem"] == "pip"
    ]
    assert len(pip_entries) == 1
    pip_entry = pip_entries[0]
    # Dependabot's pip resolver cannot regenerate these uv-compiled locks, so
    # pip version-update PRs are disabled and the advisory gates in CI are the
    # compensating control.
    assert pip_entry["open-pull-requests-limit"] == 0
    assert pip_entry["directory"] == "/"


def test_dependabot_npm_updates_target_the_frontend_lock() -> None:
    config = _load_unique(ROOT / ".github/dependabot.yml")
    npm_entries = [
        entry for entry in config["updates"]
        if entry["package-ecosystem"] == "npm"
    ]
    assert len(npm_entries) == 1
    # frontend/package-lock.json is the only npm lock in the repository, so a
    # Dependabot npm update lands directly on the lock npm ci consumes.
    assert npm_entries[0]["directory"] == "/frontend"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_advisory_gate_audits_every_python_lock(workflow: Path) -> None:
    text = workflow.read_text(encoding="utf-8")
    for lock in (
        "requirements-lock.txt",
        "requirements-dev-lock.txt",
        "requirements-linux-gui-lock.txt",
    ):
        assert lock in text, f"{workflow.name} does not audit {lock}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_advisory_gate_covers_other_platforms(workflow: Path) -> None:
    # pip-audit skips pins whose environment marker does not match the runner,
    # so a universal lock must be audited through a platform-neutral projection.
    text = workflow.read_text(encoding="utf-8")
    assert "scripts/audit_lock_all_platforms.py" in text
