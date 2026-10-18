from pathlib import Path
import os
import pytest

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# The CI/release pipeline sets this after a production `npm run build`. When set,
# a missing bundle is a hard failure: packaging a UI-less app must never pass.
REQUIRE_BUNDLE = os.environ.get("PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE") == "1"


def test_frontend_bundle_discovery():
    """Verify that frontend/dist/index.html is valid when built."""
    dist_html = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if not dist_html.is_file():
        if REQUIRE_BUNDLE:
            pytest.fail(
                "frontend/dist/index.html is missing but PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE=1; "
                "the frontend production bundle must be built before packaging."
            )
        pytest.skip("Frontend has not been compiled yet. Run 'npm run build' in frontend/ to generate it.")

    content = dist_html.read_text(encoding="utf-8")
    assert '<div id="root">' in content
    assert "<script" in content
