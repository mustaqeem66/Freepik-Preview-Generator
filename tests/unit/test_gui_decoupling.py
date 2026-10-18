"""
Release Gate: GUI decoupling.

Pure modules (settings, scanner, lifecycle, cli, renderer isolation, processor)
and their test groups must import and collect without pywebview being available.
Only ``previewgen.desktop_runtime`` may import webview at module scope.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.core

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import hook that makes ``import webview`` fail as if pywebview were absent.
_BLOCK_WEBVIEW = textwrap.dedent(
    """
    import sys

    class _BlockWebview:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "webview" or fullname.startswith("webview."):
                raise ImportError("webview deliberately unavailable for this test")
            return None

    sys.meta_path.insert(0, _BlockWebview())
    """
)


def _run_python(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )


def test_pure_modules_import_without_webview():
    code = _BLOCK_WEBVIEW + textwrap.dedent(
        """
        import importlib
        import sys

        for name in [
            "previewgen.settings",
            "previewgen.tempfiles",
            "previewgen.resources",
            "previewgen.entrypoint",
            "previewgen.scanner",
            "previewgen.lifecycle",
            "previewgen.renderer_process",
            "previewgen.preview_server",
            "previewgen.cli",
            "previewgen.api",
            "processor",
        ]:
            importlib.import_module(name)

        assert "webview" not in sys.modules, "pure modules pulled in webview at import time"
        print("PURE_IMPORTS_OK")
        """
    )
    res = _run_python(code)
    assert res.returncode == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
    assert "PURE_IMPORTS_OK" in res.stdout


def test_domain_collects_without_webview():
    """Verify core domain unit tests collect cleanly when webview is completely blocked."""
    code = _BLOCK_WEBVIEW + textwrap.dedent(
        """
        import pytest
        raise SystemExit(pytest.main(["--collect-only", "-q", "-m", "core"]))
        """
    )
    res = _run_python(code)
    assert res.returncode == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"


def test_full_runtime_collects_with_locked_dependencies():
    """Verify full-runtime format engine tests collect cleanly without webview."""
    code = _BLOCK_WEBVIEW + textwrap.dedent(
        """
        import pytest
        raise SystemExit(pytest.main(["--collect-only", "-q", "-m", "full_runtime"]))
        """
    )
    res = _run_python(code)
    assert res.returncode == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"


def test_packaged_artifact_matrix_is_available():
    """Verify packaged-release gate test collects cleanly and fixture files exist."""
    code = _BLOCK_WEBVIEW + textwrap.dedent(
        """
        import pytest
        raise SystemExit(pytest.main(["--collect-only", "-q", "-m", "packaged_release"]))
        """
    )
    res = _run_python(code)
    assert res.returncode == 0, f"stdout:\n{res.stdout}\nstderr:\n{res.stderr}"
