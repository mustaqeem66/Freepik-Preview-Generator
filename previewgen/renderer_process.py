"""
PreviewGen Renderer Process Isolation
Child-process-based rendering with hard timeout, SIGTERM/SIGKILL escalation,
and guaranteed cleanup. No webview imports.

Execution model:
    Parent batch process
      -> spawn renderer child process (own process group/session)
      -> child renders into a batch-owned temporary file
      -> parent waits with a hard timeout
      -> success: validate and atomically install
      -> timeout: terminate the child tree and delete the temporary output
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import queue as queue_module
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from processor import PreviewConfig

# Import resource limits (GUI-independent constants)
# Configure PIL image pixel limit
import contextlib

from PIL import Image

from previewgen import config as previewgen_config
from previewgen import limits, proc
from previewgen.config import MAX_IMAGE_PIXELS
from previewgen.tempfiles import create_temp_dir, safe_rmtree

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _render_worker(
    source_path: str,
    output_path: str,
    config_dict: dict[str, Any],
    result_queue: mp.Queue[dict[str, Any]],
) -> None:
    """
    Worker process that performs the actual rendering.
    Runs in an isolated child process with no access to parent resources.
    """
    # Put this worker in its own session/process group so that failure handling
    # never signals the parent batch process. On POSIX ``os.setsid`` makes the
    # child a group leader; on Windows ``taskkill /T`` handles the tree instead.
    if sys.platform != "win32":
        with contextlib.suppress(Exception):
            os.setsid()

    # Best-effort child memory ceiling so a hostile asset cannot exhaust the host
    # (Windows enforces the equivalent via the parent-owned Job Object).
    proc.apply_memory_limit(previewgen_config.MAX_RENDERER_MEMORY_BYTES)

    try:
        # Import heavy libraries inside worker to avoid loading in the parent
        from PIL import Image

        from processor import (
            MAX_IMAGE_PIXELS,
            MAX_SOURCE_FILE_BYTES,
            PreviewConfig,
            generate_file,
        )
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        source = Path(source_path)
        output = Path(output_path)
        config = PreviewConfig.from_mapping(config_dict, mode="strict-export")

        # Hard resource limits check
        if source.is_file():
            size_bytes = source.stat().st_size
            if size_bytes > MAX_SOURCE_FILE_BYTES:
                raise ValueError(
                    f"Source exceeds max size: {size_bytes // (1024 * 1024)} MB > 500 MB"
                )

        # Reject oversized assets from cheap header/estimate checks before loading.
        limits.validate_source_before_parse(source)

        # Execute render
        generate_file(source, output, config)

        # Verify output
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Output file missing or empty after render")

        with Image.open(output) as im:
            if im.format != "JPEG" or im.width <= 0 or im.height <= 0:
                raise RuntimeError(f"Invalid output: format={im.format}, size={im.size}")

        result_queue.put({
            "status": "success",
            "output_path": str(output),
            "width": im.width,
            "height": im.height,
            "size_bytes": output.stat().st_size,
        })

    except Exception as exc:
        with contextlib.suppress(Exception):
            result_queue.put({
                "status": "error",
                "error": str(exc),
                "error_type": type(exc).__name__,
            })


class RendererProcessPool:
    """
    Manages a renderer child process with hard timeout and kill escalation.
    """

    def __init__(
        self,
        max_workers: int = 1,
        default_timeout: float = 60.0,
        kill_timeout: float = 5.0,
    ) -> None:
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.kill_timeout = kill_timeout
        self._process: Any | None = None
        self._result_queue: Any | None = None
        self._cancelled = mp.Event()
        self._job: Any | None = None
        self.last_survivors: set[int] = set()

    def render(
        self,
        source_path: Path,
        output_path: Path,
        config: PreviewConfig,
        timeout_seconds: float | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """
        Render a single file in an isolated child process with hard timeout
        and guaranteed cleanup. Renders into a batch-owned temporary file and
        atomically installs on success.
        """
        timeout = timeout_seconds or self.default_timeout

        # Prepare arguments for worker
        config_dict = {
            "text": config.text,
            "position": config.position,
            "opacity": config.opacity * 100,
            "invertTriangles": config.invert_triangles,
            "solidColor": config.solid_color,
            "textColor": config.text_color,
            "hasOutline": config.has_outline,
            "outlineColor": config.outline_color,
            "outlineThickness": config.outline_thickness,
            "fontScale": config.font_scale * 100,
            "yaw": config.yaw,
            "pitch": config.pitch,
            "modelColor": config.model_color,
            "textPosX": config.text_pos_x * 100,
            "textPosY": config.text_pos_y * 100,
            "logoPath": config.logo_path,
            "logoScale": config.logo_scale * 100,
            "logoOpacity": config.logo_opacity * 100,
            "logoPosX": config.logo_pos_x * 100,
            "logoPosY": config.logo_pos_y * 100,
            "fontPath": config.font_path,
            "overwritePolicy": config.overwrite_policy,
            "outputWidth": config.output_width,
            "outputHeight": config.output_height,
        }

        # Batch-owned temporary directory co-located with the destination so the
        # final install is a same-filesystem atomic replace.
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Reject the render up front if the destination lacks room for the output.
        required_bytes = previewgen_config.EXPECTED_OUTPUT_MAX_BYTES
        export_longest = max(int(config.output_width or 0), int(config.output_height or 0))
        if export_longest > 0:
            required_bytes = max(required_bytes, limits.compute_output_requirement(export_longest))
        limits.ensure_free_disk_space(output_path.parent, required_bytes)

        temp_dir = create_temp_dir("previewgen_render_", base_dir=output_path.parent)
        temp_output = temp_dir / "render.jpg"

        self._result_queue = mp.Queue()
        self._cancelled.clear()

        try:
            # Create the Job Object before the child exists so the window in which
            # it can spawn an unmanaged descendant is only the assign() call.
            if sys.platform == "win32":
                self._job = proc.WindowsJob(previewgen_config.MAX_RENDERER_MEMORY_BYTES)

            self._process = mp.Process(
                target=_render_worker,
                args=(str(source_path), str(temp_output), config_dict, self._result_queue),
                daemon=True,
            )
            self._process.start()

            # Windows: bind the child to a Job Object so every descendant it
            # spawns is killed when the job handle is closed. A failed assign
            # leaves only the coarser taskkill fallback, so make it visible.
            if sys.platform == "win32":
                pid = self._process.pid
                if self._job is None or not self._job.active:
                    logging.warning("Windows Job Object unavailable; renderer containment is degraded")
                elif pid is None or not self._job.assign(pid):
                    logging.warning("Could not assign renderer pid %s to the Job Object", pid)

            start_time = time.monotonic()

            while True:
                # Check for external cancellation
                if is_cancelled and is_cancelled():
                    self._terminate_process_tree()
                    raise RuntimeError("Batch render cancelled by user")

                # Check for process completion
                if not self._process.is_alive():
                    break

                # Check timeout
                if (time.monotonic() - start_time) > timeout:
                    logging.warning("Render timeout for %s after %.1fs", source_path.name, timeout)
                    self._terminate_process_tree()
                    raise TimeoutError(f"Rendering exceeded {timeout}s for {source_path.name}")

                time.sleep(0.1)

            # Join to let the child's queue feeder flush before reading.
            self._process.join(timeout=self.kill_timeout)

            try:
                result = self._result_queue.get(timeout=2.0)
            except queue_module.Empty:
                exit_code = self._process.exitcode
                # Negative exit codes indicate termination by a signal (POSIX).
                if exit_code is not None and exit_code < 0:
                    raise TimeoutError("Render process terminated (timeout)") from None
                if exit_code is not None and exit_code != 0:
                    raise RuntimeError(f"Render process exited with code {exit_code}") from None
                raise RuntimeError("Render process exited without result") from None

            if result.get("status") == "error":
                raise RuntimeError(
                    f"Renderer error: {result['error']} ({result.get('error_type', 'Unknown')})"
                )

            # Validate and atomically install the batch-owned temp output.
            if not temp_output.is_file() or temp_output.stat().st_size == 0:
                raise RuntimeError("Renderer reported success but temp output is missing")

            os.replace(temp_output, output_path)
            result["output_path"] = str(output_path)
            return result

        finally:
            self._cleanup()
            safe_rmtree(temp_dir, "render temp")

    def _terminate_process_tree(self) -> None:
        """
        Terminate the renderer child *and every descendant it spawned*, escalating
        from graceful (SIGTERM / taskkill) to forceful (SIGKILL), then verify no
        descendants survived. Survivors are recorded in ``last_survivors``.
        """
        if not self._process:
            return

        self._cancelled.set()

        pid = self._process.pid
        if pid is None:
            return

        if self._process.is_alive():
            survivors = proc.terminate_process_tree(pid, kill_timeout=self.kill_timeout)
        else:
            survivors = set()

        with contextlib.suppress(Exception):
            self._process.join(timeout=self.kill_timeout)

        self.last_survivors = survivors
        if survivors:
            logging.error(
                "Renderer process tree for %s left %d surviving descendant(s)",
                pid,
                len(survivors),
            )

    def _close_job(self) -> None:
        """Close the Windows Job Object (killing any remaining descendants)."""
        job = self._job
        if job is not None:
            with contextlib.suppress(Exception):
                job.close()
            self._job = None

    def _cleanup(self) -> None:
        """Ensure process and queue are cleaned up."""
        self._cancelled.set()
        if self._process and self._process.is_alive():
            self._terminate_process_tree()
        if self._result_queue:
            try:
                while True:
                    self._result_queue.get_nowait()
            except Exception:
                pass
            try:
                self._result_queue.close()
                self._result_queue.join_thread()
            except Exception:
                pass
        self._process = None
        self._result_queue = None
        self._close_job()


def render_file_isolated(
    source_path: Path,
    output_path: Path,
    config: PreviewConfig,
    timeout_seconds: float = 60.0,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    """
    Render a file in an isolated child process with hard timeout and kill escalation.
    """
    pool = RendererProcessPool(default_timeout=timeout_seconds)
    pool.render(source_path, output_path, config, timeout_seconds, is_cancelled)

    if not Path(output_path).is_file():
        raise RuntimeError("Renderer reported success but output file is missing")


# Backward compatibility wrapper for existing callers
def render_file_with_timeout(
    source_path: Path,
    output_path: Path,
    config: PreviewConfig,
    timeout_seconds: float = 60.0,
    is_cancelled: Callable[[], bool] | None = None,
) -> None:
    """Compatibility wrapper - now uses process isolation."""
    render_file_isolated(source_path, output_path, config, timeout_seconds, is_cancelled)
