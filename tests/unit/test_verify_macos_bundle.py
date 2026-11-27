"""Structural verification for the packaged macOS application bundle."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from scripts.verify_macos_bundle import verify_bundle

pytestmark = pytest.mark.core

VERSION = "2.1.4"


def _write(path: Path, content: str = "content") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_bundle(root: Path) -> Path:
    app = root / "PreviewGen.app"
    contents = app / "Contents"
    frameworks = contents / "Frameworks"

    plist = {
        "CFBundleIdentifier": "com.zenartisan.previewgen",
        "CFBundleExecutable": "PreviewGen",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
    }
    contents.mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(plistlib.dumps(plist))

    executable = contents / "MacOS" / "PreviewGen"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"\xcf\xfa\xed\xfe")

    _write(
        frameworks / "frontend" / "dist" / "index.html",
        '<!doctype html><script type="module" src="./assets/app.js"></script>'
        '<link rel="stylesheet" href="./assets/app.css">',
    )
    _write(frameworks / "frontend" / "dist" / "assets" / "app.js", "export {};")
    _write(
        frameworks / "frontend" / "dist" / "assets" / "app.css",
        '@import "./theme.css"; body { background: url("./font.woff2"); }',
    )
    _write(frameworks / "frontend" / "dist" / "assets" / "theme.css", ":root {}")
    _write(frameworks / "frontend" / "dist" / "assets" / "font.woff2", "font")
    _write(frameworks / "previewgen" / "settings_schema.json", "{}")
    _write(frameworks / "webview" / "js" / "api.js", "// api")
    _write(frameworks / "webview" / "js" / "finish.js", "// finish")
    _write(frameworks / "setuptools" / "_vendor" / "jaraco" / "text" / "__init__.py", "# marker")
    _write(frameworks / "objc" / "_objc.cpython-312-darwin.so", "native")
    _write(frameworks / "Foundation" / "_Foundation.cpython-312-darwin.so", "native")
    _write(frameworks / "AppKit" / "_AppKit.cpython-312-darwin.so", "native")
    _write(frameworks / "WebKit" / "_WebKit.cpython-312-darwin.so", "native")
    return app


def test_verify_bundle_accepts_a_complete_app(tmp_path: Path) -> None:
    app = _make_bundle(tmp_path)

    assert verify_bundle(app, expected_version=VERSION) == []


@pytest.mark.parametrize(
    ("relative_path", "expected_message"),
    [
        ("Contents/Info.plist", "Info.plist"),
        ("Contents/MacOS/PreviewGen", "executable"),
        ("Contents/Frameworks/frontend/dist/index.html", "frontend index"),
        ("Contents/Frameworks/frontend/dist/assets/app.js", "frontend asset"),
        ("Contents/Frameworks/frontend/dist/assets/font.woff2", "frontend asset"),
        ("Contents/Frameworks/previewgen/settings_schema.json", "settings schema"),
        ("Contents/Frameworks/webview/js/api.js", "pywebview JavaScript"),
        ("Contents/Frameworks/setuptools/_vendor/jaraco/text/__init__.py", "Setuptools"),
        ("Contents/Frameworks/WebKit/_WebKit.cpython-312-darwin.so", "WebKit"),
    ],
)
def test_verify_bundle_rejects_missing_required_content(
    tmp_path: Path,
    relative_path: str,
    expected_message: str,
) -> None:
    app = _make_bundle(tmp_path)
    (app / relative_path).unlink()

    failures = verify_bundle(app, expected_version=VERSION)

    assert any(expected_message in failure for failure in failures)


def test_verify_bundle_rejects_wrong_identity_and_version(tmp_path: Path) -> None:
    app = _make_bundle(tmp_path)
    plist_path = app / "Contents" / "Info.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    plist["CFBundleIdentifier"] = "com.example.other"
    plist["CFBundleShortVersionString"] = "9.9.9"
    plist["CFBundleVersion"] = "0.0.0"
    plist_path.write_bytes(plistlib.dumps(plist))

    failures = verify_bundle(app, expected_version=VERSION)

    assert any("bundle identifier" in failure for failure in failures)
    assert any("short version" in failure for failure in failures)
    assert any("build version" in failure for failure in failures)


def test_verify_bundle_rejects_empty_or_invalid_text_resources(tmp_path: Path) -> None:
    app = _make_bundle(tmp_path)
    (app / "Contents/Frameworks/webview/js/api.js").write_text("", encoding="utf-8")
    (app / "Contents/Frameworks/previewgen/settings_schema.json").write_text("not json", encoding="utf-8")

    failures = verify_bundle(app, expected_version=VERSION)

    assert any("pywebview JavaScript" in failure for failure in failures)
    assert any("settings schema" in failure for failure in failures)


def test_verify_bundle_rejects_non_macho_executable(tmp_path: Path) -> None:
    app = _make_bundle(tmp_path)
    (app / "Contents" / "MacOS" / "PreviewGen").write_bytes(b"not macho")

    failures = verify_bundle(app, expected_version=VERSION)

    assert any("Mach-O" in failure for failure in failures)
