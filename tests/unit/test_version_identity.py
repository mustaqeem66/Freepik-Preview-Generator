"""Release identity must be consistent across packaging surfaces (P2-17)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import previewgen  # noqa: E402

pytestmark = pytest.mark.core


def test_version_matches_installer_and_frontend():
    installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
    match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', installer)
    assert match, "installer.iss is missing MyAppVersion"

    frontend = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROJECT_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))

    assert match.group(1) == previewgen.__version__
    assert frontend["version"] == previewgen.__version__
    assert lock["version"] == previewgen.__version__
    assert lock["packages"][""]["version"] == previewgen.__version__


def test_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", previewgen.__version__)
