"""Offline regressions for Dependabot alert export and sorting."""
import json

import pytest

from scripts.dependabot_report import gh_command, markdown, normalize_alerts, report_rows

pytestmark = pytest.mark.core


def _alert(number, severity="high", state="open"):
    return {
        "number": number,
        "state": state,
        "dependency": {
            "package": {"name": "example", "ecosystem": "pip"},
            "manifest_path": "requirements-lock.txt",
            "scope": "runtime",
        },
        "security_advisory": {"severity": severity, "ghsa_id": f"GHSA-test-{number}"},
        "security_vulnerability": {"vulnerable_version_range": "<2", "first_patched_version": {"identifier": "2.0"}},
    }


def test_pagination_dedupe_and_severity_order():
    alerts = normalize_alerts([[_alert(9, "low"), _alert(2, "critical")], [_alert(9, "low"), _alert(4, "high")]])
    assert [a["number"] for a in alerts] == [2, 4, 9]


def test_filters_closed_alerts_and_handles_missing_fix():
    open_alert = _alert(7)
    open_alert["security_vulnerability"]["first_patched_version"] = None
    rows = report_rows(normalize_alerts([open_alert, _alert(8, state="dismissed")]))
    assert len(rows) == 1
    assert rows[0]["firstPatchedVersion"] is None
    assert "not published" in markdown(rows)


def test_empty_response_is_valid_and_explicit():
    assert "Open Dependabot alerts (0)" in markdown(report_rows(normalize_alerts([])))


def test_malformed_alerts_fail_closed():
    with pytest.raises(ValueError, match="numeric number"):
        normalize_alerts([[{"state": "open"}]])
    with pytest.raises(ValueError, match="array"):
        normalize_alerts({"message": "Bad credentials"})


def test_command_uses_only_specific_read_only_endpoint():
    assert gh_command("owner/repo") == [
        "gh", "api", "--paginate", "--slurp",
        "repos/owner/repo/dependabot/alerts?state=open&per_page=100",
    ]
    with pytest.raises(ValueError):
        gh_command("owner/repo;rm -rf /tmp")


def test_report_contains_advisory_and_manifest():
    rows = report_rows(normalize_alerts([_alert(42)]))
    assert rows[0]["manifest"] == "requirements-lock.txt"
    assert rows[0]["ghsa"] == "GHSA-test-42"
    assert json.loads(json.dumps(rows)) == rows
