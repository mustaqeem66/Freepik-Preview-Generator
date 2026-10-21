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
