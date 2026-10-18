"""
PreviewGen Batch Runner
Walks an input folder (including nested ZIP archives), renders each supported
asset, and writes durable JSON/CSV batch reports.
"""
from __future__ import annotations

import contextlib
import datetime
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from previewgen.batch.archive import safe_extract_zip
from previewgen.batch.discovery import DiscoveryLimits, DiscoveryStats, discover_files
from previewgen.batch.reporting import write_batch_reports
from previewgen.config import (
    DISCOVERY_MAX_DEPTH,
    DISCOVERY_MAX_DIRECTORIES,
    DISCOVERY_MAX_FILES,
    DISCOVERY_TIMEOUT_SECONDS,
    SUPPORTED_EXTENSIONS,
    PreviewConfig,
)
from previewgen.errors import classify_exception
from previewgen.lock import DirectoryLock
from previewgen.renderer_process import render_file_with_timeout as _render_file_with_timeout
from previewgen.tempfiles import create_temp_dir, safe_rmtree


def process_folder(
    input_folder: Path,
    output_folder: Path,
    config: PreviewConfig,
    progress: Callable[[int, int, str], None],
    is_cancelled: Callable[[], bool],
) -> dict[str, Any]:
    input_folder = input_folder.resolve()
    output_folder = output_folder.resolve()
    # Streamed, cancellable, bounded discovery. The output directory (which may
    # be nested inside the input) is excluded so a re-run never reprocesses its
    # own artifacts, and ``maximum_files`` bounds peak memory.
    discovery_stats = DiscoveryStats()
    limits = DiscoveryLimits(
        maximum_files=DISCOVERY_MAX_FILES,
        maximum_directories=DISCOVERY_MAX_DIRECTORIES,
        timeout_seconds=DISCOVERY_TIMEOUT_SECONDS,
        max_depth=DISCOVERY_MAX_DEPTH,
    )
    sequence_id = 0

    def _report_progress(cur: int, tot: int, msg: str) -> None:
        nonlocal sequence_id
        sequence_id += 1
        import inspect
        sig = inspect.signature(progress)
        if len(sig.parameters) >= 4:
            progress(cur, tot, msg, sequence_id)
        else:
            progress(cur, tot, msg)

    def _on_discovery_progress(stats: DiscoveryStats) -> None:
        _report_progress(stats.files, 0, f"Discovering previews\u2026 ({stats.files} found)")

    raw_files = list(
        discover_files(
            input_folder,
            is_cancelled=is_cancelled,
            excluded_roots={output_folder} if output_folder != input_folder else set(),
            limits=limits,
            supported_extensions=SUPPORTED_EXTENSIONS,
            stats=discovery_stats,
            on_progress=_on_discovery_progress,
        )
    )
    cancelled = discovery_stats.cancelled

    if not raw_files and not cancelled:
        if discovery_stats.truncated:
            reasons = ", ".join(discovery_stats.reasons) or "unknown"
            raise ValueError(
                f"Discovery stopped early ({reasons}) before any supported image was found"
            )
        ext_list = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"No supported images ({ext_list}) found in the input folder")

    output_folder.mkdir(parents=True, exist_ok=True)

    # Disk-space preflight: estimate temporary and final storage separately (Finding 7)
    from previewgen.limits import estimate_batch_disk_requirements
    disk_preflight = estimate_batch_disk_requirements(raw_files, output_folder)
    if not disk_preflight["sufficient"]:
        raise OSError(disk_preflight["error"])

    start_time = time.time()
    started_at_iso = datetime.datetime.now(datetime.UTC).isoformat()
    import uuid
    batch_id = uuid.uuid4().hex[:12]

    # Centralized DirectoryLock service (Finding 8)
    dir_lock = DirectoryLock(output_folder, batch_id=batch_id)
    dir_lock.acquire()
    success = 0
    failed = 0
    skipped = 0
    errors: list[str] = []
    file_records: list[dict[str, Any]] = []
    work_items: list[tuple[Path, str]] = []
    allocated_names: set[str] = set()
    temp_dirs: list[Path] = []

    try:
        for src in raw_files:
            if is_cancelled():
                cancelled = True
                break
            if src.suffix.lower() == ".zip":
                zip_tmp = create_temp_dir("previewgen_batch_zip_")
                temp_dirs.append(zip_tmp)
                try:
                    safe_extract_zip(src, zip_tmp)
                    nested_zips = [nz for nz in zip_tmp.rglob("*.zip") if nz.is_file()]
                    for nz in nested_zips:
                        with contextlib.suppress(Exception):
                            safe_extract_zip(nz, nz.parent / nz.stem)

                    inner_files = sorted(
                        p for p in zip_tmp.rglob("*.*")
                        if p.is_file()
                        and p.suffix.lower() in SUPPORTED_EXTENSIONS
                        and p.suffix.lower() != ".zip"
                        and not any(
                            part.startswith(".") and part not in (".", "..") or part == "__MACOSX"
                            for part in p.relative_to(zip_tmp).parts
                        )
                    )
                    if not inner_files:
                        failed += 1
                        errors.append(f"{src.name}: No supported assets inside archive")
                        continue

                    for inner in inner_files:
                        rel_parts = inner.relative_to(zip_tmp).parent.parts
                        slug = f"_{'_'.join(rel_parts)}" if rel_parts else ""
                        candidate_stem = f"{src.stem}{slug}_{inner.stem}"
                        counter = 1
                        out_name = f"{candidate_stem}.jpg"
                        while out_name.lower() in allocated_names:
                            out_name = f"{candidate_stem}_{inner.suffix.lstrip('.')}_{counter}.jpg"
                            counter += 1
                        allocated_names.add(out_name.lower())
                        work_items.append((inner, out_name))
                except Exception as exc:
                    code, clean_msg = classify_exception(exc)
                    logging.warning("Archive extraction failed for %s [%s]: %s", src.name, code, exc)
                    failed += 1
                    errors.append(f"{src.name}: {clean_msg}")
            else:
                rel_parts = src.relative_to(input_folder).parent.parts
                prefix = f"{'_'.join(rel_parts)}_" if rel_parts else ""
                candidate_stem = f"{prefix}{src.stem}"
                out_name = f"{candidate_stem}.jpg"
                counter = 1
                while out_name.lower() in allocated_names:
                    out_name = f"{candidate_stem}_{src.suffix.lstrip('.')}_{counter}.jpg"
                    counter += 1
                allocated_names.add(out_name.lower())
                work_items.append((src, out_name))

        planned = len(work_items) + failed
        total = max(1, len(work_items) + failed)
        completed = failed
        # ``cancelled`` may already be set if discovery (or work-item assembly)
        # was interrupted; never reset it here.
        for item_path, out_name in work_items:
            if is_cancelled():
                cancelled = True
                break
            target_file = output_folder / out_name
            if target_file.exists():
                if config.overwrite_policy == "skip":
                    skipped += 1
                    completed += 1
                    _report_progress(completed, total, f"Skipped (exists) {out_name}")
                    continue
                elif config.overwrite_policy == "rename":
                    r_count = 1
                    while target_file.exists():
                        target_file = output_folder / f"{Path(out_name).stem}_copy{r_count}.jpg"
                        r_count += 1

            file_start = time.time()
            file_rec: dict[str, Any] = {
                "source": item_path.name,
                "output": target_file.name,
                "status": "pending",
                "duration": 0.0,
                "errorCode": None,
                "error": None,
            }
            try:
                # Checkpoint right before generating file
                if is_cancelled():
                    cancelled = True
                    file_rec["status"] = "cancelled"
                    file_records.append(file_rec)
                    break
                _render_file_with_timeout(
                    item_path, target_file, config, timeout_seconds=60.0, is_cancelled=is_cancelled
                )
                file_duration = round(time.time() - file_start, 3)
                file_rec["status"] = "success"
                file_rec["duration"] = file_duration
                file_records.append(file_rec)
                success += 1
                status = f"Created {target_file.name}"
            except Exception as exc:
                file_duration = round(time.time() - file_start, 3)
                if is_cancelled():
                    cancelled = True
                    file_rec["status"] = "cancelled"
                    file_rec["duration"] = file_duration
                    file_records.append(file_rec)
                    break
                code, clean_msg = classify_exception(exc)
                logging.warning("Render failed for %s [%s]: %s", item_path.name, code, exc)
                failed += 1
                status = f"Failed {item_path.name}"
                errors.append(f"{item_path.name}: {clean_msg}")
                file_rec["status"] = "failed"
                file_rec["duration"] = file_duration
                file_rec["errorCode"] = code
                file_rec["error"] = clean_msg
                file_records.append(file_rec)
            completed += 1
            _report_progress(completed, total, status)

    finally:
        for t in temp_dirs:
            safe_rmtree(t, "batch zip temp")
        dir_lock.release()

    finished_at_iso = datetime.datetime.now(datetime.UTC).isoformat()
    duration = round(time.time() - start_time, 2)
    processed = success + failed + skipped
    remaining = max(0, planned - processed)

    report_err_msg: str | None = None

    if cancelled:
        batch_status = "cancelled"
    elif failed > 0:
        batch_status = "completed_with_errors"
    elif discovery_stats.truncated or discovery_stats.permission_errors > 0:
        batch_status = "completed_with_warnings"
    else:
        batch_status = "completed"
    summary_payload: dict[str, Any] = {
        "batchId": batch_id,
        "startedAt": started_at_iso,
        "finishedAt": finished_at_iso,
        "status": batch_status,
        "planned": planned,
        "processed": processed,
        "remaining": remaining,
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "cancelled": cancelled,
        "truncated": discovery_stats.truncated,
        "truncationReasons": list(discovery_stats.reasons),
        "discovered": discovery_stats.files,
        "discoveryTruncated": discovery_stats.truncated,
        "discoveryReasons": list(discovery_stats.reasons),
        "discoveryPermissionErrors": discovery_stats.permission_errors,
        "inaccessibleDirectories": list(discovery_stats.inaccessible_directories),
        "generationStatus": batch_status,
        "reportStatus": "pending",
        "reportError": report_err_msg,
        "errors": errors,
        "duration": duration,
        "files": file_records,
    }

    # P0 Issue 7 / Phase 4: Version reports by batch ID and publish the
    # ``latest`` pointer only after both JSON and CSV are safely written.
    report_result = write_batch_reports(output_folder, summary_payload, file_records)
    summary_payload["reportStatus"] = report_result["status"]
    summary_payload["reportError"] = report_result["errorCode"]
    summary_payload["reportId"] = batch_id
    summary_payload["reportJson"] = Path(report_result["jsonPath"]).name
    summary_payload["reportCsv"] = Path(report_result["csvPath"]).name
    return summary_payload
