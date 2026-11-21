"""Security hardening regressions: loopback server, CSV/AppleScript escaping."""
from __future__ import annotations

import csv
import http.client
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.batch.reporting import write_batch_reports
from previewgen.dialogs import applescript_string
from previewgen.preview_server import PreviewFileServer

pytestmark = pytest.mark.core


def _get(port: int, path: str, host: str) -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", host)
        conn.endheaders()
        return conn.getresponse().status
    finally:
        conn.close()


def test_preview_server_rejects_foreign_host_and_bad_token():
    server = PreviewFileServer()
    try:
        url = server.publish_jpeg(b"\xff\xd8\xff\xd9")
        path = "/" + "/".join(url.split("/")[3:])
        port = server._port

        assert _get(port, path, f"127.0.0.1:{port}") == 200
        assert _get(port, path, f"localhost:{port}") == 200
        assert _get(port, path, "evil.example") == 404
        assert _get(port, path, f"evil.example:{port}") == 404
        assert _get(port, path, f"127.0.0.1:{port + 1}") == 404
        assert _get(port, "/wrong-token/preview_000001.jpg", f"127.0.0.1:{port}") == 404
    finally:
        server.stop()


def test_csv_report_neutralises_formula_injection(tmp_path):
    records = [
        {
            "source": "=cmd|calc.png",
            "output": "+SUM(1,1).jpg",
            "status": "@evil",
            "duration": 0.1,
            "errorCode": "-1",
            "error": "=HYPERLINK(\"http://evil\")",
        }
    ]
    result = write_batch_reports(tmp_path, {"batchId": "sec01234"}, records)
    with open(result["csvPath"], newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[1][0].startswith("'=")
    assert rows[1][1].startswith("'+")
    assert rows[1][2].startswith("'@")
    assert rows[1][4].startswith("'-")
    assert rows[1][5].startswith("'=")
    assert not any(cell.startswith(("=", "+", "@")) for cell in rows[1])


def test_applescript_string_escapes_quotes_backslashes_and_newlines():
    quoted = applescript_string('say "hi" \\ there\nnext')
    assert quoted == '"say \\"hi\\" \\\\ there next"'
    assert not quoted.endswith("\n")


@pytest.mark.parametrize("bad_name", ['a"b', "a\\b", "a\nb"])
def test_applescript_roundtrip_is_a_single_literal(bad_name):
    quoted = applescript_string(bad_name)
    assert quoted.startswith('"') and quoted.endswith('"')
    assert "\n" not in quoted


def test_report_payload_remains_valid_json_after_hardening(tmp_path):
    result = write_batch_reports(tmp_path, {"batchId": "json1234"}, [])
    assert json.loads(Path(result["jsonPath"]).read_text(encoding="utf-8"))["batchId"] == "json1234"
