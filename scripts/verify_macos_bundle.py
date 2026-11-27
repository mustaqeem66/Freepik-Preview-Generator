#!/usr/bin/env python3
"""Verify that a frozen PreviewGen macOS app contains every startup resource.

This is intentionally a structural gate. A successful PyInstaller exit proves
only that files were collected; it does not prove that WKWebView can find the
frontend, pywebview can inject its bridge, or the frozen bootstrap has the
vendored modules it imports.
"""

from __future__ import annotations

import argparse
import platform
import plistlib
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

BUNDLE_IDENTIFIER = "com.zenartisan.previewgen"
BUNDLE_EXECUTABLE = "PreviewGen"
MACHO_MAGICS = {
    b"\xcf\xfa\xed\xfe",  # thin 64-bit
    b"\xce\xfa\xed\xfe",  # thin 32-bit
    b"\xca\xfe\xba\xbe",  # universal fat
    b"\xca\xfe\xba\xbf",  # 64-bit fat
    b"\xbe\xba\xfe\xca",  # reversed fat
    b"\xbf\xfa\xfe\xca",  # reversed 64-bit fat
}


class _AssetParser(HTMLParser):
    """Collect local script, style, font, and image references."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.references.append(values["src"] or "")
        elif tag == "link" and values.get("href"):
            self.references.append(values["href"] or "")
        elif tag in {"img", "source"} and values.get("src"):
            self.references.append(values["src"] or "")


def _source_version() -> str:
    from previewgen import __version__

    return __version__


def _has_file(path: Path, patterns: tuple[str, ...]) -> bool:
    if path.is_file():
        return True
    search_root = path if path.is_dir() else path.parent
    for pattern in patterns:
        for match in search_root.glob(pattern):
            if match.is_file():
                return True
    return False


def _frontend_references(index_path: Path) -> tuple[list[str], list[str]]:
    """Return referenced local assets and parser/HTML errors."""
    try:
        html = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [], [f"frontend index cannot be read: {exc}"]
    parser = _AssetParser()
    try:
        parser.feed(html)
    except Exception as exc:
        return [], [f"frontend index cannot be parsed: {exc}"]

    root = index_path.parent.resolve()
    references: list[str] = []
    errors: list[str] = []
    for raw in parser.references:
        parsed = urlparse(raw)
        if parsed.scheme or parsed.netloc or raw.startswith(("data:", "#")):
            continue
        path_text = unquote(parsed.path)
        if not path_text:
            continue
        candidate = (root / path_text.lstrip("/")).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"frontend asset escapes the bundle: {raw}")
            continue
        references.append(str(candidate))
    return references, errors


def _architecture_failures(executable: Path, expected_arch: str | None) -> list[str]:
    if not expected_arch:
        return []
    lipo = shutil.which("lipo")
    if not lipo:
        return [f"cannot verify {expected_arch} architecture: lipo is unavailable"]
    try:
        result = subprocess.run(
            [lipo, "-archs", str(executable)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"cannot verify executable architecture: {exc}"]
    if result.returncode != 0:
        return [f"cannot verify executable architecture: {result.stderr.strip()}"]
    architectures = {part.strip() for part in result.stdout.split() if part.strip()}
    if expected_arch not in architectures:
        return [
            f"executable architecture does not include {expected_arch}: {', '.join(sorted(architectures)) or 'unknown'}"
        ]
    return []


def verify_bundle(
    app_path: Path,
    expected_version: str | None = None,
    expected_arch: str | None = None,
) -> list[str]:
    """Return every structural failure in a PreviewGen macOS app bundle."""
    failures: list[str] = []
    app = Path(app_path)
    contents = app / "Contents"
    frameworks = contents / "Frameworks"
    expected_version = expected_version or _source_version()

    if not app.is_dir():
        return [f"application bundle is missing: {app}"]

    info_path = contents / "Info.plist"
    info: dict[str, object] = {}
    if not info_path.is_file():
        failures.append("Contents/Info.plist is missing")
    else:
        try:
            loaded = plistlib.loads(info_path.read_bytes())
            if isinstance(loaded, dict):
                info = loaded
            else:
                failures.append("Contents/Info.plist is not a dictionary")
        except (OSError, plistlib.InvalidFileException) as exc:
            failures.append(f"Contents/Info.plist cannot be read: {exc}")

    if info.get("CFBundleIdentifier") != BUNDLE_IDENTIFIER:
        failures.append(f"bundle identifier must be {BUNDLE_IDENTIFIER!r}, found {info.get('CFBundleIdentifier')!r}")
    if info.get("CFBundleExecutable") != BUNDLE_EXECUTABLE:
        failures.append(f"bundle executable must be {BUNDLE_EXECUTABLE!r}, found {info.get('CFBundleExecutable')!r}")
    if str(info.get("CFBundleShortVersionString", "")) != expected_version:
        failures.append(
            f"bundle version must be {expected_version!r}, found {info.get('CFBundleShortVersionString')!r}"
        )

    executable = contents / "MacOS" / BUNDLE_EXECUTABLE
    if not executable.is_file():
        failures.append("application executable is missing")
    else:
        try:
            magic = executable.read_bytes()[:4]
        except OSError as exc:
            failures.append(f"application executable cannot be read: {exc}")
        else:
            if magic not in MACHO_MAGICS:
                failures.append("application executable is not a Mach-O binary")
        failures.extend(_architecture_failures(executable, expected_arch))

    index_path = frameworks / "frontend" / "dist" / "index.html"
    if not index_path.is_file():
        failures.append("packaged frontend index is missing")
    else:
        references, reference_errors = _frontend_references(index_path)
        failures.extend(reference_errors)
        for reference in references:
            if not Path(reference).is_file():
                failures.append(f"packaged frontend asset is missing: {Path(reference).name}")

    if not (frameworks / "previewgen" / "settings_schema.json").is_file():
        failures.append("packaged settings schema is missing")

    webview_js = frameworks / "webview" / "js"
    if not _has_file(webview_js / "api.js", ("api.js", "api.*.js")):
        failures.append("packaged pywebview JavaScript is missing")
    if not _has_file(webview_js / "finish.js", ("finish.js", "finish.*.js")):
        failures.append("packaged pywebview JavaScript is missing")

    setuptools_root = frameworks / "setuptools"
    pkg_resources_root = frameworks / "pkg_resources"
    if not any(
        _has_file(root, ("_vendor/jaraco/**/*", "vendor/jaraco/**/*", "extern/jaraco/**/*"))
        for root in (setuptools_root, pkg_resources_root)
    ):
        failures.append("frozen Setuptools vendored jaraco content is missing")

    native_requirements = {
        "objc": (frameworks / "objc", "_objc*.so"),
        "Foundation": (frameworks / "Foundation", "_Foundation*.so"),
        "AppKit": (frameworks / "AppKit", "_AppKit*.so"),
        "WebKit": (frameworks / "WebKit", "_WebKit*.so"),
    }
    for name, (root, pattern) in native_requirements.items():
        if not _has_file(root, (pattern,)):
            failures.append(f"frozen {name} native module is missing")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, help="Path to PreviewGen.app")
    parser.add_argument("--expected-version", default=None)
    parser.add_argument(
        "--expected-arch",
        default=platform.machine() if sys.platform == "darwin" else None,
    )
    args = parser.parse_args(argv)
    failures = verify_bundle(
        args.app,
        expected_version=args.expected_version,
        expected_arch=args.expected_arch,
    )
    if failures:
        for failure in failures:
            print(f"FATAL: {failure}")
        return 1
    print(f"PASS: macOS application bundle is complete: {args.app}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
