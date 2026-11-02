#!/usr/bin/env python3
"""Read *open* Dependabot alerts via the user's own authenticated GitHub CLI.

Read-only: never dismisses alerts, changes dependencies, or starts CI.
No GitHub token is accepted as an argument or written to an output file.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_REPO = "mustaqeem66/Freepik-Preview-Generator"
SEVERITIES = {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def gh_command(repo: str) -> list[str]:
    if not REPO_PATTERN.fullmatch(repo) or ".." in repo:
        raise ValueError("--repo must be a GitHub owner/repository name")
    return [
        "gh", "api", "--paginate", "--slurp",
        f"repos/{repo}/dependabot/alerts?state=open&per_page=100",
    ]


def normalize_alerts(payload: Any) -> list[dict[str, Any]]:
    """Accept the standard REST list or gh --paginate --slurp list of pages."""
    if not isinstance(payload, list):
        raise ValueError("Expected an array of Dependabot alerts")
    alerts: dict[int, dict[str, Any]] = {}
    for page in payload:
        items = page if isinstance(page, list) else [page]
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("number"), int):
                raise ValueError("Malformed Dependabot alert: missing numeric number")
            if item.get("state") not in (None, "open"):
                continue
            alerts[item["number"]] = item
    return sorted(
        alerts.values(),
        key=lambda a: (
            SEVERITIES.get(str((a.get("security_advisory") or {}).get("severity", "")).lower(), 4),
            a["number"],
        ),
    )


def _field(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def report_rows(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for alert in alerts:
        patched = _field(alert, "security_vulnerability", "first_patched_version", "identifier")
        rows.append({
            "number": alert["number"],
            "severity": _field(alert, "security_advisory", "severity") or "unknown",
            "package": _field(alert, "dependency", "package", "name") or "unknown",
            "ecosystem": _field(alert, "dependency", "package", "ecosystem") or "unknown",
            "manifest": _field(alert, "dependency", "manifest_path") or "unknown",
            "scope": _field(alert, "dependency", "scope") or "unknown",
            "vulnerableRange": _field(alert, "security_vulnerability", "vulnerable_version_range") or "unknown",
            "firstPatchedVersion": patched or None,
            "ghsa": _field(alert, "security_advisory", "ghsa_id") or None,
            "url": alert.get("html_url"),
        })
    return rows


def markdown(rows: list[dict[str, Any]]) -> str:
    def cell(value: Any) -> str:
        return str(value if value is not None else "not published").replace("|", "\\|").replace("\n", " ")

    output = [
        f"# Open Dependabot alerts ({len(rows)})",
        "",
        "| # | Severity | Package | Ecosystem | Manifest | Vulnerable range | First patch | Advisory |",
        "| ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        values = [
            row["number"], row["severity"], row["package"], row["ecosystem"],
            row["manifest"], row["vulnerableRange"], row["firstPatchedVersion"], row["ghsa"],
        ]
        output.append("| " + " | ".join(cell(v) for v in values) + " |")
    output.extend(["", "Read-only snapshot; verify each alert and test dependency fixes locally."])
    return "\n".join(output) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--input", type=Path, help="Use a saved gh api JSON export instead of contacting GitHub")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write report to this local file (otherwise stdout)")
    args = parser.parse_args(argv)
    try:
        if args.input:
            payload = json.loads(args.input.read_text(encoding="utf-8"))
        else:
            command = gh_command(args.repo)
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode:
                raise RuntimeError(
                    f"GitHub CLI could not fetch alerts (exit {result.returncode}). "
                    "Run 'gh auth login' and confirm repo security-alert access. "
                    "No alert was marked as resolved."
                )
            payload = json.loads(result.stdout)
        rows = report_rows(normalize_alerts(payload))
        rendered = (
            json.dumps({"repository": args.repo, "openAlerts": len(rows), "alerts": rows}, indent=2) + "\n"
            if args.format == "json" else markdown(rows)
        )
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
            print(f"Saved {len(rows)} open alert(s) to {args.output}")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
