"""Structural guards for the CI workflow and Dependabot configuration.

These checks catch configuration shapes that parse as YAML but behave in a way
the repository does not intend: duplicate mapping keys, an advisory gate that
skips a lock, or a Dependabot ecosystem whose limit contradicts its comment.

The checks use only the standard library: PyYAML is not a declared project
dependency, and a test must not depend on a package that only happens to be
installed on a developer's machine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = (
    ROOT / ".github/workflows/build.yml",
    ROOT / ".github/workflows/pr-checks.yml",
)
DEPENDABOT = ROOT / ".github/dependabot.yml"

# A YAML mapping key at the start of a line, ignoring indentation.
_MAPPING_KEY = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:(?=\s|$)")


def _mapping_blocks(text: str) -> list[tuple[int, str]]:
    """Return (indent, key) for every mapping key in a YAML document."""
    return [
        (len(match.group("indent")), match.group("key"))
        for match in _MAPPING_KEY.finditer(text)
    ]


def _duplicate_keys(text: str) -> list[str]:
    """Find mapping keys that are declared twice within the same block.

    A duplicate key in one mapping is ambiguous: YAML loaders may keep the
    first value, keep the last, or reject the document. GitHub's workflow and
    Dependabot parsers are not guaranteed to agree, so the repository must not
    contain one.
    """
    # Track the keys seen at each indentation level and the line that closed
    # that level, so a sibling block does not look like a duplicate.
    open_blocks: list[tuple[int, set[str], int]] = []
    duplicates: list[str] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.split("#", 1)[0].rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" \t"))
        # Close every block that this line dedented out of.
        while open_blocks and open_blocks[-1][0] > indent:
            open_blocks.pop()
        # A list item starts a new scope; the keys after it belong to that item.
        if stripped.lstrip().startswith("- "):
            open_blocks.append((indent + 2, set(), lineno))
            continue
        match = _MAPPING_KEY.match(stripped)
        if match is None:
            continue
        key = match.group("key")
        if open_blocks and open_blocks[-1][0] == indent:
            seen = open_blocks[-1][1]
            if key in seen:
                duplicates.append(f"{key} (line {lineno})")
            seen.add(key)
        else:
            open_blocks.append((indent, {key}, lineno))
    return duplicates


def test_workflows_have_no_duplicate_yaml_keys() -> None:
    for workflow in WORKFLOWS:
        duplicates = _duplicate_keys(workflow.read_text(encoding="utf-8"))
        assert not duplicates, f"{workflow.name} has duplicate keys: {duplicates}"


def test_dependabot_config_has_no_duplicate_yaml_keys() -> None:
    duplicates = _duplicate_keys(DEPENDABOT.read_text(encoding="utf-8"))
    assert not duplicates, f".github/dependabot.yml has duplicate keys: {duplicates}"


def test_dependabot_pip_updates_are_disabled() -> None:
    text = DEPENDABOT.read_text(encoding="utf-8")
    pip_block = _ecosystem_block(text, "pip")
    # Dependabot's pip resolver cannot regenerate these uv-compiled locks, so
    # pip version-update PRs are disabled and the advisory gates in CI are the
    # compensating control.
    assert "open-pull-requests-limit: 0" in pip_block
    assert "open-pull-requests-limit: 5" not in pip_block


def test_dependabot_npm_updates_target_the_frontend_lock() -> None:
    text = DEPENDABOT.read_text(encoding="utf-8")
    npm_block = _ecosystem_block(text, "npm")
    # frontend/package-lock.json is the only npm lock in the repository, so a
    # Dependabot npm update lands directly on the lock npm ci consumes.
    assert 'directory: "/frontend"' in npm_block


def _ecosystem_block(text: str, ecosystem: str) -> str:
    """Return the YAML block that configures one Dependabot ecosystem."""
    marker = f"- package-ecosystem: {ecosystem}"
    start = text.find(marker)
    assert start != -1, f"no {ecosystem} ecosystem in the Dependabot config"
    following = text.find("- package-ecosystem:", start + len(marker))
    return text[start:following if following != -1 else len(text)]


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
