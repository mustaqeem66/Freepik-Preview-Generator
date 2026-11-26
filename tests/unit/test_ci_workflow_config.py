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


def test_the_release_job_signs_its_checksum_file() -> None:
    """A checksum published beside the artifact proves nothing on its own.

    An attacker who can replace the download can replace SHA256SUMS.txt too.
    A detached GPG signature over the checksum file is what lets a user
    verify the artifacts against a key they already trust, independently of
    the release channel.

    PreviewGen is a free, MIT-licensed project that does not buy a signing
    certificate, so the GPG key is optional: when one is configured the
    checksums are signed, and when none is configured the release still ships
    the SHA-256 file. The signature machinery must therefore remain present
    and self-verifying rather than being removed.
    """
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")

    assert "--detach-sign" in text, "the release must produce a detached signature"
    assert "gpg --batch --verify" in text, "the produced signature must be verified"
    assert "SHA256SUMS.txt.asc" in text, "the signature must be published with the release"
    assert "GPG_PRIVATE_KEY" in text, "the release must read the signing key when one exists"
    # The signature must be attached only when it was actually produced.
    assert "if [ -f SHA256SUMS.txt.asc ] && [ -f previewgen-signing-key.asc ]; then" in text, (
        "the release must attach the detached signature only when it exists"
    )


def test_windows_artifacts_are_signature_verified_after_signing() -> None:
    """`signtool sign` exiting zero is not proof of a valid signature.

    The macOS job already verifies its own signature; the Windows job did not,
    so an unsigned or partially signed artifact could be published unnoticed.

    The check applies to a build that was actually signed. PreviewGen ships
    unsigned by default, so a build with no certificate configured has nothing
    to verify; a build that did sign must read the signature back.
    """
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")

    assert text.count("Get-AuthenticodeSignature") >= 2, (
        "both the executable and the installer must have their signature read back"
    )
    assert 'if ($status.Status -ne "Valid")' in text, "a non-Valid Authenticode status must fail the job"
    assert "TimeStamperCertificate" in text, "an untimestamped signature expires with the certificate and must fail"
    # Both verification steps must skip an unsigned build instead of failing.
    assert text.count('if ("${{ secrets.WINDOWS_CERTIFICATE }}" -eq "")') >= 2, (
        "an unsigned build must not be required to carry a valid signature"
    )


def test_the_release_does_not_require_a_paid_code_signing_certificate() -> None:
    """PreviewGen is free and MIT-licensed; a paid certificate must not gate it.

    Signing and notarization require a paid certificate or an Apple Developer
    membership, which this project does not buy. The Windows and macOS builds
    therefore sign when a certificate is configured and ship unsigned
    otherwise, and the release must not refuse to publish for their absence.
    """
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")

    for refusal in (
        "Release tag build requires WINDOWS_CERTIFICATE",
        "Release tag build requires MACOS_CERTIFICATE",
        "Release tag build requires APPLE_ID",
        "A release must ship a GPG-signed checksum file",
    ):
        assert refusal not in text, f"the release must not refuse to publish: {refusal!r}"
    # The signing machinery must remain, so a configured certificate is used.
    assert 'if ("${{ secrets.WINDOWS_CERTIFICATE }}" -ne "")' in text
    assert 'if [ -n "${{ secrets.MACOS_CERTIFICATE }}" ]' in text
    assert 'if [ -n "${{ secrets.APPLE_ID }}" ]' in text


def test_linux_build_verifies_the_frozen_webkit_bundle() -> None:
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")

    assert "python scripts/verify_linux_webkit_bundle.py dist/PreviewGen" in text


def test_linux_build_delegates_graphics_libraries_to_the_host() -> None:
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")
    strip_index = text.index("rm -f dist/PreviewGen/_internal/libepoxy.so.0 dist/PreviewGen/_internal/libgbm.so.1")
    verify_index = text.index("python scripts/verify_linux_webkit_bundle.py dist/PreviewGen")

    assert strip_index < verify_index


def test_linux_build_collects_setuptools_vendor_modules() -> None:
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")

    assert "--collect-all setuptools" in text


def test_linux_clean_machine_gate_covers_a_newer_distribution_webkit() -> None:
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")
    clean_machine_job = text.split("clean-machine-test:", 1)[1]

    assert "os: ubuntu-22.04" in clean_machine_job
    assert "os: ubuntu-24.04" in clean_machine_job
    assert "name: native-csp-${{ matrix.artifact }}-${{ matrix.os }}" in text


def test_the_windows_installer_verifies_more_than_a_self_consistent_checksum() -> None:
    """install.ps1 must not trust a checksum fetched from the same release.

    A checksum file downloaded next to the artifact proves only that the two
    agree. Verifying the detached signature over the checksums, and reading
    back the installer's Authenticode signature, are what establish who
    produced the file.
    """
    installer = ROOT / "install.ps1"
    text = installer.read_text(encoding="utf-8")

    assert "SHA256SUMS.txt.asc" in text, "the installer must fetch the detached signature"
    assert "previewgen-signing-key.asc" in text, "the installer must fetch the public key"
    assert "--verify" in text, "the installer must verify the detached signature"
    assert "Get-AuthenticodeSignature" in text, "the installer must read back the setup binary's Authenticode signature"


def test_linux_release_verifies_the_final_downloadable_appimage() -> None:
    """The onedir gate cannot prove what AppImage assembly produced."""
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")

    package_index = text.index("ARCH=x86_64 ./appimagetool")
    verify_index = text.index("python scripts/verify_linux_webkit_bundle.py PreviewGen-Linux.AppImage")
    upload_index = text.index("name: ${{ matrix.artifact }}", package_index)

    assert package_index < verify_index < upload_index


def test_linux_clean_machine_gate_requires_a_newer_host_webkit_package() -> None:
    """Distribution labels do not prove the WebKitGTK package versions differ."""
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")
    clean_machine_job = text.split("clean-machine-test:", 1)[1]

    assert "webkit_manifest.json" in clean_machine_job
    assert "dpkg --compare-versions" in clean_machine_job
    assert "gt" in clean_machine_job
    assert "FATAL: acceptance host WebKitGTK package is not newer" in clean_machine_job


def test_linux_clean_machine_gate_covers_x11_xvfb_and_wayland_sessions() -> None:
    """Each display backend must independently reach the frontend-ready marker."""
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")
    clean_machine_job = text.split("clean-machine-test:", 1)[1]

    for scenario in ("xvfb", "x11", "wayland"):
        assert f"gui_ready_{scenario}.txt" in clean_machine_job
    assert "GDK_BACKEND=x11" in clean_machine_job
    assert "GDK_BACKEND=wayland" in clean_machine_job
    assert "EGL_PLATFORM=x11" in clean_machine_job
    assert "EGL_PLATFORM=wayland" in clean_machine_job
    assert "__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json" in clean_machine_job
    assert "WEBKIT_DISABLE_DMABUF_RENDERER=1" in clean_machine_job
    assert "WEBKIT_DISABLE_COMPOSITING_MODE=1" in clean_machine_job
    assert "LIBGL_ALWAYS_SOFTWARE=1" in clean_machine_job
    assert "appimage-extract/squashfs-root/AppRun --gui-smoke-test" in clean_machine_job
    assert "weston --backend=headless-backend.so" in clean_machine_job
    assert "WKBundleInitialize" in clean_machine_job
    assert "WebKitWebProcess" in clean_machine_job
    assert "Xvfb :99 -screen 0 1280x1024x24" in clean_machine_job
    assert 'if [ "${{ matrix.os }}" != "ubuntu-24.04" ]; then' in clean_machine_job
    assert "xvfb-run -a" not in clean_machine_job, (
        "the headless WebKit process must connect to a direct Xvfb server without an xauth cookie"
    )


def test_linux_setuptools_collection_is_attached_to_the_pyinstaller_command() -> None:
    """A collection flag elsewhere in the workflow cannot fix frozen bootstrap."""
    build = ROOT / ".github/workflows/build.yml"
    text = build.read_text(encoding="utf-8")
    pyinstaller_block = next(body for _, body in _run_blocks(text) if "pyinstaller --noconsole" in body)

    assert "--collect-all setuptools" in pyinstaller_block
