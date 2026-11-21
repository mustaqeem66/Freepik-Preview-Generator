#!/usr/bin/env python3
"""Report whether ``main`` has moved past the most recent published release.

A green build says the tree is healthy. It says nothing about whether a user
who runs the install script receives that tree. The install scripts resolve
``/releases/latest``, so the only code a user can obtain is whatever was last
published -- every merge after that point is invisible to them.

That gap went unnoticed for 139 commits: the security hardening, the renderer
repairs and the WCAG contrast fixes all sat on ``main`` while the newest
published release stayed at the old build. Nothing failed, because nothing was
checking.

This script closes the gap. It compares the version declared in the tree
against the newest published release and reports the difference. It never
fails the build on its own -- a stale release is a publishing decision, not a
code defect -- but it makes the difference visible in the job log, and
``--strict`` turns it into a hard failure for a release-cut pipeline.

Usage:
    python scripts/check_release_freshness.py            # report only
    python scripts/check_release_freshness.py --strict   # fail when stale
    python scripts/check_release_freshness.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPO = "Mustaqeem66/Freepik-Preview-Generator"
API_ROOT = "https://api.github.com"


def _tree_version() -> str:
    """Read the version the tree declares, without importing the package."""
    source = (PROJECT_ROOT / "previewgen" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', source, re.MULTILINE)
    if not match:
        raise SystemExit("previewgen/__init__.py does not declare __version__")
    return match.group(1)


def _version_key(version: str) -> tuple[int, ...]:
    """Order a dotted numeric version; a non-numeric part sorts lowest."""
    parts: list[int] = []
    for part in version.split("."):
        parts.append(int(part) if part.isdigit() else 0)
    return tuple(parts)


def _latest_published_release(repo: str) -> tuple[str | None, str | None]:
    """Return (tag, published_at) for the newest published release.

    The GitHub ``/releases/latest`` endpoint skips drafts and prereleases,
    which matches exactly what the install scripts resolve: a user running
    ``install.ps1`` receives the newest *published* release and nothing else.
    """
    url = f"{API_ROOT}/repos/{repo}/releases/latest"
    request = urllib.request.Request(url, headers={"User-Agent": "PreviewGen-Release-Freshness"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, f"could not reach the GitHub API: {exc}"
    return payload.get("tag_name"), payload.get("published_at")


def _unreleased_commit_count(repo: str, tag: str | None) -> int | None:
    """Count commits on ``main`` that are not in the published release tag."""
    if not tag:
        return None
    local_tag = subprocess.run(
        ["git", "rev-parse", "--verify", f"{tag}^{{commit}}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if local_tag.returncode != 0:
        return None
    count = subprocess.run(
        ["git", "rev-list", "--count", f"{tag}..origin/main"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if count.returncode != 0:
        return None
    try:
        return int(count.stdout.strip())
    except ValueError:
        return None


def _check_tag(tag: str, tree_version: str) -> int:
    """Validate the tag being cut against the version the tree declares.

    A tag build is the moment a release is created, so the published release
    cannot exist yet -- demanding that it does would make the check circular
    and fail the very workflow that creates it.

    The meaningful invariant is narrower and stronger: the tag must name the
    version the tree declares. A tag that disagrees with the tree would
    publish artifacts whose own version metadata contradicts the tag, and a
    user reading the release page would see one version while the app
    reported another.
    """
    tag_version = tag.lstrip("vV")
    if tag_version == tree_version:
        print(f"Release tag {tag} matches the tree version {tree_version}.")
        return 0
    print(
        f"Release tag mismatch: the tag is {tag} but the tree declares {tree_version}. "
        "The published artifact would contradict the tag.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/name")
    parser.add_argument("--strict", action="store_true", help="exit non-zero when the tree is ahead")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON")
    parser.add_argument(
        "--tag",
        default=None,
        help="validate this release tag against the tree version instead of comparing to the published release",
    )
    args = parser.parse_args(argv)

    tree_version = _tree_version()

    if args.tag:
        return _check_tag(args.tag, tree_version)

    latest_tag, published_at = _latest_published_release(args.repo)

    if latest_tag is None:
        message = published_at or "the latest published release could not be determined"
        if args.as_json:
            print(json.dumps({"ok": False, "tree_version": tree_version, "error": message}, indent=2))
        else:
            print(f"Release freshness: UNKNOWN -- {message}", file=sys.stderr)
        # An unknown release state is not proof of staleness, so it must not
        # fail a build. A strict caller still gets a non-zero exit.
        return 1 if args.strict else 0

    latest_version = latest_tag.lstrip("vV")
    unreleased = _unreleased_commit_count(args.repo, latest_tag)

    # A version bump alone does not prove the release is current. The tree
    # version and the published tag can match while main carries commits that
    # were never released -- which is exactly the state this project sat in
    # for 139 commits: the version stayed 2.1.2, the published release stayed
    # 2.1.2, and every merge in between was invisible to anyone installing.
    #
    # So the tree is stale when the version moved past the release, or when
    # main carries commits the release does not contain.
    version_ahead = _version_key(tree_version) > _version_key(latest_version)
    commits_ahead = bool(unreleased)
    stale = version_ahead or commits_ahead

    result = {
        "ok": not stale,
        "tree_version": tree_version,
        "latest_release": latest_tag,
        "latest_published_at": published_at,
        "unreleased_commits": unreleased,
        "stale": stale,
    }

    if args.as_json:
        print(json.dumps(result, indent=2))
    else:
        if stale:
            details = []
            if version_ahead:
                details.append(f"the tree is {tree_version} but the release is {latest_tag}")
            if commits_ahead:
                details.append(f"{unreleased} commit(s) on main are not in {latest_tag}")
            print("Release freshness: STALE -- " + "; ".join(details))
            print(
                f"Users running install.ps1 or install.sh receive {latest_tag}. "
                "Publish a release to make the current tree installable."
            )
        else:
            print(
                f"Release freshness: OK -- the tree ({tree_version}) matches the newest published "
                f"release ({latest_tag}) and main carries no unreleased commits."
            )

    return 1 if (stale and args.strict) else 0


if __name__ == "__main__":
    raise SystemExit(main())
