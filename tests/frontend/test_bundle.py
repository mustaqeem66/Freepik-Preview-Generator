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


def test_production_webview_csp_when_bundle_exists():
    """A production bundle must carry the security policy before its scripts."""
    html_path = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if not html_path.is_file():
        if REQUIRE_BUNDLE:
            pytest.fail("Production bundle missing; CSP cannot be verified.")
        pytest.skip("Build the frontend to verify shipped CSP.")

    content = html_path.read_text(encoding="utf-8")
    marker = 'data-previewgen-csp="production"'
    assert content.count(marker) == 1, "Production CSP missing or duplicated"
    assert content.index(marker) < content.index("<script"), "CSP must precede scripts"
    assert 'http-equiv="Content-Security-Policy"' in content
    assert "script-src 'self' 'unsafe-eval'" in content
    assert "script-src 'self' 'unsafe-eval' 'unsafe-inline'" not in content
    assert "img-src 'self' data: blob: http://127.0.0.1:*" in content
    assert "connect-src 'self' http://127.0.0.1:*" in content
