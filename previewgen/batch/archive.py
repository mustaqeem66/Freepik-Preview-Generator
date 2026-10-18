"""
PreviewGen Batch Archive Extraction
Zip-Slip-safe ZIP extraction with resource, path length, and depth limits.
"""
from __future__ import annotations

from pathlib import Path

from previewgen import config as previewgen_config
from previewgen import limits


def safe_extract_zip(zip_path: Path | str, target_dir: Path | str) -> list[Path]:
    """
    Safely extract a ZIP archive into target_dir with strict Zip-Slip protection,
    resource limits, and path depth/length validation.
    Returns list of extracted file Paths.
    """
    import zipfile

    max_members = previewgen_config.MAX_ZIP_MEMBERS
    max_member_bytes = previewgen_config.MAX_MEMBER_BYTES
    max_total_bytes = previewgen_config.MAX_TOTAL_BYTES
    max_compression_ratio = previewgen_config.MAX_COMPRESSION_RATIO
    max_path_length = previewgen_config.MAX_PATH_LENGTH
    max_path_depth = previewgen_config.MAX_PATH_DEPTH

    source = Path(zip_path)
    root = Path(target_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    extracted_files: list[Path] = []
    total_extracted_bytes = 0
    member_count = 0

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
