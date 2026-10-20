"""
PreviewGen Batch Archive Extraction
Zip-Slip-safe ZIP extraction with resource, path length, and depth limits.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from previewgen import config as previewgen_config
from previewgen import limits

# How many levels of archive-inside-archive are unpacked. Nested bombs multiply
# every per-archive budget by the number of levels, so the tree is capped.
MAX_NESTED_DEPTH = 2


def _ensure_running(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled is not None and is_cancelled():
        raise ValueError("Extraction cancelled")


def safe_extract_zip(
    zip_path: Path | str,
    target_dir: Path | str,
    *,
    is_cancelled: Callable[[], bool] | None = None,
    depth: int = 0,
    max_depth: int = MAX_NESTED_DEPTH,
    budget_bytes: int | None = None,
) -> list[Path]:
    """Safely extract a ZIP archive into ``target_dir``.

    Zip-Slip protected, resource limited, and depth validated. ``budget_bytes``
    caps the bytes this call may write, so a caller unpacking a tree of nested
    archives can share one total across the whole tree instead of granting each
    archive a fresh allowance. ``depth``/``max_depth`` stop archive-in-archive
    recursion. Returns the list of extracted file paths.
    """
    import zipfile

    if depth > max_depth:
        raise ValueError(f"Nested archive depth exceeds {max_depth} levels")

    max_members = previewgen_config.MAX_ZIP_MEMBERS
    max_member_bytes = previewgen_config.MAX_MEMBER_BYTES
    max_total_bytes = previewgen_config.MAX_TOTAL_BYTES
    if budget_bytes is not None:
        max_total_bytes = min(max_total_bytes, max(0, budget_bytes))
    max_compression_ratio = previewgen_config.MAX_COMPRESSION_RATIO
    max_path_length = previewgen_config.MAX_PATH_LENGTH
    max_path_depth = previewgen_config.MAX_PATH_DEPTH

    source = Path(zip_path)
    root = Path(target_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    extracted_files: list[Path] = []
    total_extracted_bytes = 0
    member_count = 0

    _ensure_running(is_cancelled)
    with zipfile.ZipFile(source, "r") as zf:
        infolist = zf.infolist()
        if len(infolist) > max_members:
            raise ValueError(f"Archive exceeds maximum member limit ({len(infolist)} > {max_members})")

        # Validate the declared total uncompressed size and free disk space up
        # front, before extracting a single byte.
        declared_total = sum(member.file_size for member in infolist)
        if declared_total > max_total_bytes:
            raise ValueError(
                f"Archive declares {declared_total} uncompressed bytes, exceeding limit of {max_total_bytes}"
            )
        limits.ensure_free_disk_space(root, declared_total)

        for member in infolist:
            _ensure_running(is_cancelled)
            member_count += 1
            if member_count > max_members:
                raise ValueError(f"Archive member count exceeded limit ({max_members})")

            if member.file_size > max_member_bytes:
                raise ValueError(
                    f"Member '{member.filename}' uncompressed size {member.file_size} exceeds limit {max_member_bytes}"
                )

            if member.compress_size > 0:
                ratio = member.file_size / member.compress_size
                if ratio > max_compression_ratio and member.file_size > 1_000_000:
                    raise ValueError(f"Suspicious compression ratio ({ratio:.1f}) in '{member.filename}'")

            parts = Path(member.filename).parts
            if member.filename.startswith(("/", "\\")) or ".." in parts:
                raise ValueError(f"Archive member escapes extraction root (Zip-Slip attempt): {member.filename}")

            if (
                member.is_dir()
                or any(p.startswith(".") and p not in (".", "..") or p == "__MACOSX" for p in parts)
                or member.filename.lower().endswith((".ds_store", "thumbs.db", "desktop.ini"))
            ):
                continue

            if len(member.filename) > max_path_length:
                raise ValueError(f"Path length exceeds {max_path_length} characters: {member.filename}")
            if len(parts) > max_path_depth:
                raise ValueError(f"Path depth exceeds {max_path_depth} levels: {member.filename}")

            target = (root / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(
                    f"Archive member escapes extraction root (Zip-Slip attempt): {member.filename}"
                ) from exc

            bytes_written = 0
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                while True:
                    _ensure_running(is_cancelled)
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_member_bytes:
                        raise ValueError(f"Member '{member.filename}' exceeded size limit during extraction")
                    dst.write(chunk)

            total_extracted_bytes += bytes_written
            if total_extracted_bytes > max_total_bytes:
                raise ValueError(f"Total archive size exceeds limit of {max_total_bytes} bytes")

            extracted_files.append(target)

    return extracted_files
