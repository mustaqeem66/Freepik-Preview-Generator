"""Canonical output-destination resolution shared by single and batch exports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from previewgen.errors import ErrorCode


class DestinationError(ValueError):
    """A destination rejection with a stable bridge error code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


def same_folder_enabled(config: Any) -> bool:
    """Read ``sameFolder`` without letting a malformed value change the default."""
    if not isinstance(config, dict):
        return True
    value = config.get("sameFolder", True)
    return value is not False


def resolve_output_folder(output_folder: Any, same_folder: bool, same_folder_target: Path) -> Path:
    """Resolve the one destination both export paths use.

    ``same_folder_target`` is the source folder for a batch and the asset's own
    folder (or archive folder for a ZIP member) for a single export. When
    ``same_folder`` is off the renderer must supply an output folder; there is
    deliberately no fallback, so the UI and backend can never disagree about
    where files will be written.
    """
    if same_folder:
        return same_folder_target.resolve()
    if not isinstance(output_folder, str) or not output_folder.strip():
        raise DestinationError(ErrorCode.OUTPUT_FOLDER_REQUIRED)
    return Path(output_folder.strip()).resolve()


def protect_source_destinations(
    destination: Path,
    source_files: set[Path],
    reserved_output_names: set[str] | None = None,
) -> Path:
    """Never export onto an original input file, regardless of overwrite policy.

    For regular JPEG inputs, the requested output can be the original source.
    The same is true when a PNG and JPG in the same folder share a stem:
    processing the PNG first must not overwrite the JPG before reading it.
    Source files are canonicalized once before batch work begins. If the
    candidate resolves to any source, allocate an unused, unreserved
    `_preview` name; never silently delete or mutate a source.
    """
    destination = Path(destination)
    if destination.resolve() not in source_files:
        return destination
    blocked = reserved_output_names or set()
    stem = destination.stem
    suffix = destination.suffix
    attempt = 0
    while True:
        attempt += 1
        filename = f"{stem}_preview{attempt if attempt > 1 else ''}{suffix}"
        candidate = destination.with_name(filename)
        if (not candidate.exists() and
                candidate.name.lower() not in blocked and
                candidate.resolve() not in source_files):
            return candidate
