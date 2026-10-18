"""
PreviewGen Batch Reporting
Writes durable, per-batch-ID JSON and CSV reports, then publishes a small
``latest`` pointer only after both files are safely in place. This keeps report
history intact and prevents a crash between the two writes from producing a
mixed (new JSON + old CSV) pair.
"""
from __future__ import annotations

import contextlib
import csv
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from previewgen.config import REPORT_LATEST, REPORT_PREFIX, REPORT_RETENTION
from previewgen.errors import ErrorCode


def _prune_old_reports(output_folder: Path, retention: int) -> None:
    """Best-effort retention: keep only the ``retention`` newest report pairs."""
    if retention <= 0:
        return
    try:
        json_reports = sorted(
            (
                p
                for p in output_folder.glob(f"{REPORT_PREFIX}*.json")
                if p.is_file() and p.name != REPORT_LATEST
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception as exc:
        logging.debug("Report retention scan skipped: %s", exc)
        return

    for stale in json_reports[retention:]:
        for candidate in (stale, stale.with_suffix(".csv")):
            try:
                candidate.unlink(missing_ok=True)
            except Exception as exc:
                logging.debug("Could not prune old report %s: %s", candidate, exc)


def write_batch_reports(
    output_folder: Path,
    summary_payload: dict[str, Any],
    file_records: list[dict[str, Any]],
    retention: int = REPORT_RETENTION,
) -> dict[str, Any]:
    """
    Persist ``previewgen-report-<batch-id>.json`` and ``.csv``, then atomically
    publish ``previewgen-report-latest.json`` pointing at both.

    Returns a dict with ``status`` ("written"/"failed"), ``errorCode``, and the
    resolved report paths. Never raises: report failures must not abort a batch.
    """
    batch_id = str(summary_payload.get("batchId") or "unknown")
    json_path = output_folder / f"{REPORT_PREFIX}{batch_id}.json"
    csv_path = output_folder / f"{REPORT_PREFIX}{batch_id}.csv"
    latest_path = output_folder / REPORT_LATEST

    # Temp names are unique per writer so two instances (or overlapping batches)
    # can never clobber each other's in-flight temp files mid-``replace``.
    tag = f"{os.getpid()}_{threading.get_ident()}_{uuid.uuid4().hex[:8]}"
    json_tmp = output_folder / f".{REPORT_PREFIX}{batch_id}.{tag}.json.tmp"
    csv_tmp = output_folder / f".{REPORT_PREFIX}{batch_id}.{tag}.csv.tmp"
    latest_tmp = output_folder / f".{REPORT_LATEST}.{tag}.tmp"

    result: dict[str, Any] = {
        "status": "pending",
        "errorCode": None,
        "jsonPath": str(json_path),
        "csvPath": str(csv_path),
        "latestPath": str(latest_path),
    }

    try:
        json_tmp.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

        with open(csv_tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "output", "status", "duration_sec", "error_code", "error"])
            for rec in file_records:
                writer.writerow([
                    Path(rec.get("source", "")).name,
                    Path(rec.get("output", "")).name,
                    rec.get("status"),
                    rec.get("duration"),
                    rec.get("errorCode") or "",
                    rec.get("error") or "",
                ])

        # Both payloads are complete on disk as temp files; now promote each
        # atomically. Per-batch filenames guarantee prior reports are untouched.
        json_tmp.replace(json_path)
        csv_tmp.replace(csv_path)

        # Publish the pointer only after both reports are safely installed.
        latest_payload = {
            "batchId": batch_id,
            "json": json_path.name,
            "csv": csv_path.name,
            "finishedAt": summary_payload.get("finishedAt"),
            "status": summary_payload.get("status"),
            "generationStatus": summary_payload.get("generationStatus"),
            "truncated": summary_payload.get("truncated"),
            "truncationReasons": summary_payload.get("truncationReasons"),
        }
        latest_tmp.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")
        # On Windows, replace() can fail with WinError 5 Access Denied if another thread is reading
        # or concurrently replacing the same latest pointer file; retry with exponential backoff.
        for attempt in range(5):
            try:
                latest_tmp.replace(latest_path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (2 ** attempt))

        result["status"] = "written"
        _prune_old_reports(output_folder, retention)
    except Exception as exc:
        logging.warning("Could not persist durable batch reports: %s", exc)
        result["status"] = "failed"
        result["errorCode"] = ErrorCode.REPORT_WRITE_FAILED
    finally:
        for tmp in (json_tmp, csv_tmp, latest_tmp):
            with contextlib.suppress(Exception):
                tmp.unlink(missing_ok=True)

    return result
