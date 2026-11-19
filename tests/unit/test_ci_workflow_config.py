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
    return [(len(match.group("indent")), match.group("key")) for match in _MAPPING_KEY.finditer(text)]


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
    return text[start : following if following != -1 else len(text)]


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


# Syntax that only a POSIX shell accepts. A `run:` block that uses any of it
# must either declare `shell: bash` or be restricted to a single OS, because
# the default shell on windows-latest is PowerShell and these fail to parse.
#
# `$(...)` is deliberately excluded: PowerShell uses it as a subexpression, so
# it is not by itself a portability problem. The constructs below are the ones
# that make PowerShell raise a ParserError.
POSIX_ONLY = (
    re.compile(r"^\s*for\s+\w+\s+in\s+.*;\s*do\b", re.M),
    re.compile(r"^\s*done\s*$", re.M),
    re.compile(r"\bset\s+-[eux]+\s+pipefail\b"),
    re.compile(r"^\s*export\s+\w+=", re.M),
    re.compile(r"^\s*(source|\.)\s+\S", re.M),
    re.compile(r"\bchmod\s+[+-]x\b"),
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\|\|\s*true\b"),
)


def _run_blocks(text: str) -> list[tuple[int, str]]:
    """Return (body start line number, body) for every `run:` block.

    The line number is the first line of the block's body, so a caller can
    walk backwards from it to find the step's own `if:`/`shell:` keys.
    """
    blocks: list[tuple[int, str]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*(\|.*|>.*|)$", lines[index])
        if match is None:
            index += 1
            continue
        indent = len(match.group(1))
        body_start = index + 1
        body: list[str] = []
        index += 1
        while index < len(lines):
            line = lines[index]
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            body.append(line)
            index += 1
        blocks.append((body_start, "\n".join(body)))
    return blocks


def _step_context(text: str, body_start: int) -> str:
    """Return the `if:`/`shell:` lines that guard the step owning body_start.

    A step's keys can appear in any order, so the search walks back to the
    start of the step (the `- name:` / `- uses:` list item) and collects every
    `if:` and `shell:` key inside it.

    It then collects the enclosing job's own `if:`, because a step can be
    confined to one OS by the job it belongs to rather than by its own guard.
    Indentation distinguishes the two levels: job keys sit at four spaces and
    step keys at eight, so a guard on an earlier *step* can never be mistaken
    for a guard on the *job*.
    """
    lines = text.splitlines()
    context: list[str] = []

    # Step-level keys: indent 8, between the step's list item and its body.
    # The step's own list item ("      - name: ...") marks the lower bound;
    # its keys sit between that marker and the run body.
    for index in range(body_start - 1, max(-1, body_start - 30), -1):
        line = lines[index]
        stripped = line.strip()
        if re.match(r"^ {6}- ", line):
            break
        if line.startswith(" " * 8) and not line.startswith(" " * 9):
            if stripped.startswith("if:") or stripped.startswith("shell:"):
                context.append(stripped)
        elif stripped.startswith("-"):
            break

    # Job-level keys: indent 4, between the job header and its `steps:` key.
    for index in range(body_start - 1, max(-1, body_start - 500), -1):
        line = lines[index]
        stripped = line.strip()
        if stripped == "steps:":
            continue
        if re.match(r"^ {2}[A-Za-z0-9_-]+:\s*$", line):
            break  # reached the enclosing job header
        if line.startswith(" " * 4) and not line.startswith(" " * 5) and stripped.startswith("if:"):
            context.append(stripped)
            break
    return " ".join(context)


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_no_posix_only_syntax_runs_under_powershell(workflow: Path) -> None:
    """A `run:` block must not contain POSIX-only syntax unless it is guarded.

    The build workflow runs on windows-latest, where the default shell is
    PowerShell. A bash `for ...; do ... done` loop is a parse error there, so
    the whole job fails before it can do anything useful. This test failed to
    exist while the advisory gate used such a loop, and the Windows release
    build failed because of it.
    """
    text = workflow.read_text(encoding="utf-8")
    for line_number, body in _run_blocks(text):
        if not body.strip():
            continue
        offenders = [pattern.pattern for pattern in POSIX_ONLY if pattern.search(body)]
        if not offenders:
            continue
        context = _step_context(text, line_number)
        # Either an explicit POSIX shell, or a guard that confines the step to
        # an OS whose default shell is POSIX. A Windows-only step is also safe:
        # PowerShell is the default there and no POSIX syntax can run.
        uses_bash = "shell: bash" in context
        confined_to_posix_os = re.search(r"if:\s*runner\.os\s*==\s*'(Linux|macOS)'", context)
        assert uses_bash or confined_to_posix_os, (
            f"{workflow.name}:{line_number} uses POSIX-only syntax {offenders} "
            f"without 'shell: bash' or a single-OS guard (guard: {context!r})"
        )
