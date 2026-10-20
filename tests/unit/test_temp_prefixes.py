"""Every PreviewGen temp directory must be covered by stale-cleanup prefixes (P1-4).

``cleanup_stale_temp_dirs`` only inspects directories whose name starts with a
registered prefix. Prefixes added at call sites without updating the registry
leak forever after a crash, so this test derives the call-site prefixes from the
source tree and asserts they are all registered.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.tempfiles import PREVIEWGEN_PREFIXES  # noqa: E402

pytestmark = pytest.mark.core

_CALL_RE = re.compile(
    r"(?:mkdtemp|create_temp_dir|TemporaryDirectory)\(\s*(?:prefix\s*=\s*)?f?[\"']([^\"']+)[\"']"
)


def _source_prefixes() -> set[str]:
    prefixes: set[str] = set()
    for path in (PROJECT_ROOT / "previewgen").rglob("*.py"):
        for match in _CALL_RE.finditer(path.read_text(encoding="utf-8")):
            literal = match.group(1)
            # f-strings such as ``f"previewgen_scan_{scan_id}_"``: the static
            # portion is what cleanup matches on.
            prefixes.add(literal.split("{", 1)[0])
    return prefixes


def test_all_temp_prefixes_are_registered_for_cleanup():
    unregistered = {
        prefix
        for prefix in _source_prefixes()
        if not any(prefix.startswith(known) for known in PREVIEWGEN_PREFIXES)
    }
    assert not unregistered, f"temp prefixes missing from PREVIEWGEN_PREFIXES: {sorted(unregistered)}"


def test_registered_prefixes_are_unique_and_terminated():
    assert len(PREVIEWGEN_PREFIXES) == len(set(PREVIEWGEN_PREFIXES))
    assert all(prefix.startswith("previewgen_") and prefix.endswith("_") for prefix in PREVIEWGEN_PREFIXES)
