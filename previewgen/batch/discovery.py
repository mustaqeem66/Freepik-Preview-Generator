"""
Bounded, cancellable filesystem discovery for batch processing.

The batch runner must never block uninterruptibly on a filesystem traversal. A
naive ``input.rglob("*.*")`` + ``sorted(...)`` materialises every path before the
first cancellation check, which is unusable on slow network shares, cloud-backed
folders, permission-heavy trees, or directories containing symlink cycles.

``discover_files`` instead streams candidate files lazily while:

* honouring a caller-supplied cancellation predicate at every directory and file,
* refusing to follow symbolic links (loop / escape protection),
* excluding resolved roots (e.g. an output directory nested inside the input),
* enforcing file, directory, depth, and wall-clock limits,
* reporting progress, and
* handling permission/OS errors explicitly instead of aborting the walk.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PROGRESS_INTERVAL = 200


@dataclass
class DiscoveryLimits:
    """Hard upper bounds so a pathological tree can never hang or exhaust memory."""

    maximum_files: int = 100_000
    maximum_directories: int = 50_000
    timeout_seconds: float = 120.0
    max_depth: int = 15


@dataclass
class DiscoveryStats:
    """Mutable, caller-owned record of what discovery actually did."""

    files: int = 0
    directories: int = 0
    skipped: int = 0
    permission_errors: int = 0
    inaccessible_directories: list[str] = field(default_factory=list)
    cancelled: bool = False
    truncated: bool = False
    reasons: list[str] = field(default_factory=list)


def _is_within(path: Path, roots: tuple[Path, ...]) -> bool:
    """True if ``path`` (already resolved) is one of ``roots`` or nested under it."""
    return any(path == root or root in path.parents for root in roots)


def _resolve_safely(path: Path) -> Path | None:
    try:
        return path.resolve()
    except OSError:
        return None


def discover_files(
    root: Path,
    *,
    is_cancelled: Callable[[], bool],
    excluded_roots: Iterable[Path],
    limits: DiscoveryLimits,
    supported_extensions: Iterable[str],
    stats: DiscoveryStats | None = None,
    on_progress: Callable[[DiscoveryStats], None] | None = None,
    progress_interval: int = DEFAULT_PROGRESS_INTERVAL,
) -> Iterator[Path]:
    """
    Yield supported files under ``root`` in deterministic order.

    The traversal is a top-down ``os.walk`` (symlinks are never followed) with
    per-entry cancellation checks and quota accounting. ``stats`` is mutated in
    place so the caller can distinguish a clean finish from one that stopped
    because it was cancelled, hit a limit, or was cut short by the deadline.
    """
    stats = stats if stats is not None else DiscoveryStats()
    allowed = {ext.lower() for ext in supported_extensions}
    excluded: list[Path] = []
    for candidate in excluded_roots:
        resolved = _resolve_safely(candidate)
        if resolved is not None:
            excluded.append(resolved)
    excluded_tuple = tuple(excluded)

    start_time = time.monotonic()

    def _on_error(err: OSError) -> None:
        stats.permission_errors += 1
        stats.skipped += 1
        stats.truncated = True
        if "permission_denied" not in stats.reasons:
            stats.reasons.append("permission_denied")
        fn = getattr(err, "filename", None)
        if fn:
            try:
                rel = str(Path(fn).relative_to(root))
            except Exception:
                rel = Path(fn).name
        else:
            rel = "?"
        if rel not in stats.inaccessible_directories:
            stats.inaccessible_directories.append(rel)
        logging.warning("Discovery could not access directory %s: %s", rel, err)
    def _stop(code: str, detail: str) -> None:
        stats.truncated = True
        if code not in stats.reasons:
            stats.reasons.append(code)
        logging.warning("Discovery truncated [%s]: %s", code, detail)

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False, onerror=_on_error):
        if is_cancelled():
            stats.cancelled = True
            logging.info("Discovery cancelled at %s", dirpath)
            return

        if stats.directories >= limits.maximum_directories:
            _stop("maximum_directories", f"directory cap reached ({limits.maximum_directories})")
            return
        if time.monotonic() - start_time > limits.timeout_seconds:
            _stop("maximum_time", f"time limit reached ({limits.timeout_seconds}s)")
            return

        current = Path(dirpath)
        rel_depth = len(current.relative_to(root).parts)
        if rel_depth >= limits.max_depth:
            if dirnames:
                _stop("maximum_depth", f"depth cap reached ({limits.max_depth})")
            dirnames[:] = []

        kept_dirs: list[str] = []
        for name in sorted(dirnames):
            if name.startswith(".") or name == "__MACOSX":
                continue
            child = current / name
            if child.is_symlink():
                stats.skipped += 1
                continue
            resolved = _resolve_safely(child)
            if resolved is not None and _is_within(resolved, excluded_tuple):
                stats.skipped += 1
                continue
            kept_dirs.append(name)
        dirnames[:] = kept_dirs
        stats.directories += 1

        for name in sorted(filenames):
            if is_cancelled():
                stats.cancelled = True
                logging.info("Discovery cancelled at %s", dirpath)
                return
            if name.startswith(".") or name == "Thumbs.db":
                continue
            file_path = current / name
            if file_path.suffix.lower() not in allowed:
                continue
            if file_path.is_symlink():
                resolved = _resolve_safely(file_path)
                root_resolved = _resolve_safely(root)
                if (
                    resolved is None
                    or not resolved.is_file()
                    or root_resolved is None
                    or not _is_within(resolved, (root_resolved,))
                    or _is_within(resolved, excluded_tuple)
                ):
                    stats.skipped += 1
                    continue
            else:
                resolved = _resolve_safely(file_path)
                if resolved is None or _is_within(resolved, excluded_tuple):
                    stats.skipped += 1
                    continue

            stats.files += 1
            if stats.files > limits.maximum_files:
                stats.files = limits.maximum_files
                _stop("maximum_files", f"file cap reached ({limits.maximum_files})")
                return

            yield file_path

            if on_progress is not None and stats.files % progress_interval == 0:
                on_progress(stats)

    if on_progress is not None:
        on_progress(stats)
