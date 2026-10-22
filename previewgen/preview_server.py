"""
PreviewGen Preview File Server
GUI-independent loopback HTTP server that serves on-demand preview JPEGs.

Instead of transferring preview images as base64 through the pywebview JS
bridge (which inflates memory and the IPC payload), previews are written to a
session temp directory and exposed over ``http://127.0.0.1:<port>/<token>/``.
The frontend then loads them with a plain ``<img src>``.

Security notes:
    * bound to loopback (127.0.0.1) only, on an ephemeral port
    * every URL carries an unguessable per-session token
    * only files directly inside the session temp directory are served
    * path traversal and directory listing are rejected
"""
from __future__ import annotations

import contextlib
import http.server
import logging
import secrets
import socket
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from previewgen.tempfiles import create_temp_dir, safe_rmtree

_KEEP_NEWEST = 2  # retain the current + previous preview so the <img> never 404s mid-switch
_MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB maximum disk consumption for cached previews
_MAX_FILE_AGE_SECONDS = 300.0  # 5 minutes maximum age for superseded preview frames


class _PreviewRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "PreviewGenPreview/1.0"

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover - silence stderr spam
        pass

    def do_GET(self) -> None:
        server = getattr(self.server, "preview_server", None)
        if server is None:
            self.send_error(404, "Not found")
            return
        server._serve(self)

    def do_HEAD(self) -> None:
        self.do_GET()


class PreviewFileServer:
    """Serves preview JPEGs from a private loopback HTTP endpoint."""
    _serializable = False  # never reachable from window.pywebview.api


    def __init__(self) -> None:
        self._root: Path | None = None
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._token = secrets.token_urlsafe(24)
        self._counter = 0
        self._port = 0
        self._lock = threading.Lock()
        # Reference counts per preview handle (filename). A preview addressed by
        # several consumers survives until the last one releases it.
        self._refs: dict[str, int] = {}

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        """Start the server on a loopback ephemeral port (idempotent)."""
        if self._httpd is not None:
            return
        self._root = create_temp_dir("previewgen_preview_")
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _PreviewRequestHandler)
        httpd.daemon_threads = True
        httpd.preview_server = self
        self._httpd = httpd
        self._port = int(httpd.server_address[1])
        self._thread = threading.Thread(
            target=httpd.serve_forever, name="preview-http", daemon=True
        )
        self._thread.start()
        self._wait_until_accepting()
        logging.info("Preview file server listening on 127.0.0.1:%d", self._port)

    def _wait_until_accepting(self, timeout: float = 2.0) -> None:
        """Block briefly until the loopback port actually accepts connections.

        On some kernels (notably WSL2) a freshly bound listening socket can
        refuse a connection for a few milliseconds. Waiting here guarantees a
        published URL is immediately fetchable by the webview.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self._port), timeout=0.25):
                    return
            except OSError:
                time.sleep(0.01)

    def publish_jpeg(self, data: bytes) -> str:
        """Persist a preview JPEG and return the loopback URL that serves it."""
        with self._lock:
            self.start()
            assert self._root is not None and self._httpd is not None
            self._counter += 1
            name = f"preview_{self._counter:06d}.jpg"
            target = self._root / name
            temp_path = self._root / f".{name}.tmp"
            temp_path.write_bytes(data)
            temp_path.replace(target)

            # Prune previews using composite limits: count, age, and total bytes
            # (Finding 6). Only *additional* references taken via ``retain_jpeg``
            # protect a frame from count/byte eviction; the age limit still
            # applies so a dropped handle can never pin a stale frame forever.
            now = time.time()
            existing = sorted(self._root.glob("preview_*.jpg"), key=lambda p: p.name)
            for handle in list(self._refs):
                if not (self._root / handle).is_file():
                    self._refs.pop(handle, None)
            retained = {h for h, count in self._refs.items() if count > 0}
            to_delete: set[Path] = (
                {p for p in existing[:-_KEEP_NEWEST] if p.name not in retained}
                if len(existing) > _KEEP_NEWEST
                else set()
            )
            # Candidates for age and bytes eviction (active frame existing[-1] is never pruned)
            candidates = [p for p in existing[:-1] if p not in to_delete]
            total_bytes = sum(p.stat().st_size for p in existing if p.is_file() and p not in to_delete)
            for p in candidates:
                try:
                    st = p.stat()
                    expired = now - st.st_mtime > _MAX_FILE_AGE_SECONDS
                    over_budget = total_bytes > _MAX_TOTAL_BYTES and p.name not in retained
                    if expired or over_budget:
                        to_delete.add(p)
                        total_bytes -= st.st_size
                except OSError:
                    to_delete.add(p)
            for stale in to_delete:
                with contextlib.suppress(Exception):
                    stale.unlink(missing_ok=True)
                    self._refs.pop(stale.name, None)

            return f"http://127.0.0.1:{self._port}/{self._token}/{name}"

    def _resolve_preview(self, handle: str) -> tuple[str, Path] | None:
        """Resolve a handle (bare preview id or full loopback URL) to a safe path."""
        if self._root is None or not isinstance(handle, str):
            return None
        try:
            text = handle.strip()
            after = urlparse(text).path if "://" in text else text
            parts = [segment for segment in after.split("/") if segment]
            if len(parts) == 2 and parts[0] == self._token:
                name = unquote(parts[1])
            elif len(parts) == 1:
                name = unquote(parts[0])
            else:
                return None
            if not name or "/" in name or "\\" in name or ".." in name:
                return None
            root = self._root.resolve()
            target = (self._root / name).resolve()
            target.relative_to(root)
            return name, target
        except Exception:
            return None

    def retain_jpeg(self, handle: str) -> bool:
        """Take an additional reference on an existing preview handle."""
        with self._lock:
            resolved = self._resolve_preview(handle)
            if resolved is None:
                return False
            name, target = resolved
            if not target.is_file():
                return False
            self._refs[name] = self._refs.get(name, 0) + 1
            return True

    def release_jpeg(self, handle: str, force: bool = False) -> bool:
        """Release one reference to a preview handle.

        Accepts either a bare preview id or the full loopback URL. Extra
        references taken via :meth:`retain_jpeg` keep the file alive; it is
        deleted only when the last such reference is released (or ``force`` is
        set). This means one consumer releasing a shared URL cannot break an
        image another consumer is still displaying. Returns ``True`` when a file
        was actually removed.
        """
        with self._lock:
            resolved = self._resolve_preview(handle)
            if resolved is None:
                return False
            name, target = resolved

            count = self._refs.get(name, 0)
            if count > 0 and not force:
                self._refs[name] = count - 1
                return False
            self._refs.pop(name, None)

            if not target.is_file():
                return False
            with contextlib.suppress(OSError):
                target.unlink()
                return True
            return False

    def stop(self) -> None:
        """Shut the server down and remove the session preview directory."""
        session_id = self._token[:8] if self._token else "unbound"
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception as exc:
                logging.warning("Preview server [%s] shutdown exception: %s", session_id, exc)
            try:
                self._httpd.server_close()
            except Exception as exc:
                logging.warning("Preview server [%s] server_close exception: %s", session_id, exc)
        if self._thread is not None:
            try:
                self._thread.join(timeout=3.0)
                if self._thread.is_alive():
                    logging.warning("Preview server [%s] background thread did not exit within 3.0s", session_id)
            except Exception as exc:
                logging.warning("Preview server [%s] thread join exception: %s", session_id, exc)
        if self._root is not None:
            try:
                safe_rmtree(self._root, f"preview server temp [{session_id}]")
                if self._root.exists():
                    logging.warning(
                        "Preview server [%s] root directory %s still exists after cleanup", session_id, self._root
                    )
            except Exception as exc:
                logging.warning("Preview server [%s] root cleanup exception: %s", session_id, exc)
        self._httpd = None
        self._thread = None
        self._root = None

    # -- request handling -------------------------------------------------

    def _serve(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        path = urlparse(handler.path).path
        parts = [segment for segment in path.split("/") if segment]
        if len(parts) != 2 or parts[0] != self._token or self._root is None:
            handler.send_error(404, "Not found")
            return

        filename = unquote(parts[1])
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            handler.send_error(404, "Not found")
            return

        try:
            resolved = (self._root / filename).resolve()
            resolved.relative_to(self._root.resolve())
        except Exception:
            handler.send_error(404, "Not found")
            return

        if not resolved.is_file():
            handler.send_error(404, "Not found")
            return

        file_size = resolved.stat().st_size
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(file_size))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.end_headers()
        if handler.command != "HEAD":
            with resolved.open("rb") as stream:
                while chunk := stream.read(64 * 1024):
                    handler.wfile.write(chunk)
