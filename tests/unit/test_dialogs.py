"""AppleScript literal encoding used by the fatal-error dialog (NEW-5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from previewgen.dialogs import applescript_string

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def test_escapes_quotes_backslashes_and_newlines():
    quoted = applescript_string('say "hi" \\ there\nnext')
    assert quoted == '"say \\"hi\\" \\\\ there next"'
    assert "\n" not in quoted


@pytest.mark.parametrize("bad", ['a"b', "a\\b", "a\nb", 'x" & (do shell script "rm -rf /") & "'])
def test_payload_cannot_break_out_of_the_literal(bad):
    quoted = applescript_string(bad)
    assert quoted.startswith('"') and quoted.endswith('"')
    assert '"' not in quoted[1:-1].replace('\\"', "")
    assert "\n" not in quoted


def test_fatal_error_dialog_uses_the_shared_encoder():
    source = (PROJECT_ROOT / "previewgen" / "desktop_runtime.py").read_text(encoding="utf-8")
    assert "from previewgen.dialogs import applescript_string" in source
    assert 'display dialog "{message}"' not in source
