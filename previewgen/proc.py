"""
PreviewGen process-tree utilities.

A renderer (or the CAD/Blender helper it launches) may spawn its own children.
Terminating only the direct child leaves descendants running, leaking memory and
locking output files. This module provides, per platform:

* descendant tracking (``descendant_pids``),
* escalating whole-tree termination (``terminate_process_tree``) that runs the
  tree down and reports any survivor,
* a Windows Job Object owner (``WindowsJob``) whose close kills the entire tree,
* a POSIX/Windows memory ceiling (``apply_memory_limit``),
* a subprocess runner that kills the whole tree on timeout
  (``run_with_tree_timeout``).
"""
from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import time

_IS_WINDOWS = sys.platform == "win32"


def _read_ppid(stat_contents: str) -> int | None:
    """Parse the parent pid from ``/proc/<pid>/stat`` (comm may contain spaces)."""
    rparen = stat_contents.rfind(")")
    if rparen < 0:
        return None
    fields = stat_contents[rparen + 2:].split()
    if len(fields) < 2:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


def _ppid_map_posix() -> dict[int, int]:
    mapping: dict[int, int] = {}
    if os.path.isdir("/proc"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                with open(f"/proc/{pid}/stat", encoding="latin-1") as fh:
                    ppid = _read_ppid(fh.read())
            except OSError:
                continue
            if ppid is not None:
                mapping[pid] = ppid
        return mapping

    # macOS / BSD fallback without /proc.
    with contextlib.suppress(Exception):
        out = subprocess.run(
            ["ps", "-Ao", "pid=,ppid="], capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            bits = line.split()
            if len(bits) >= 2:
                with contextlib.suppress(ValueError):
                    mapping[int(bits[0])] = int(bits[1])
    return mapping


if _IS_WINDOWS:  # pragma: no cover - exercised on Windows CI only
    import ctypes
    from ctypes import wintypes

    _TH32CS_SNAPPROCESS = 0x00000002
    _PROCESS_TERMINATE = 0x0001
    _SYNCHRONIZE = 0x00100000
    _WAIT_TIMEOUT = 0x00000102
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    def _ppid_map_windows() -> dict[int, int]:
        mapping: dict[int, int] = {}
        k32 = ctypes.__dict__["windll"].kernel32
        k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        snap = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap in (0, _INVALID_HANDLE_VALUE):
            return mapping
        try:
            entry = _PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
            ok = k32.Process32First(ctypes.c_void_p(snap), ctypes.byref(entry))
            while ok:
                mapping[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                ok = k32.Process32Next(ctypes.c_void_p(snap), ctypes.byref(entry))
        finally:
            k32.CloseHandle(ctypes.c_void_p(snap))
        return mapping


def _ppid_map() -> dict[int, int]:
    return _ppid_map_windows() if _IS_WINDOWS else _ppid_map_posix()


def is_alive(pid: int) -> bool:
    """Best-effort liveness probe that does not signal the target."""
    if pid <= 0 or pid == os.getpid():
        return pid == os.getpid()
    if _IS_WINDOWS:  # pragma: no cover - Windows only
        try:
            k32 = ctypes.__dict__["windll"].kernel32
            handle = k32.OpenProcess(_SYNCHRONIZE, False, pid)
            if not handle:
                return False
            try:
                return k32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return True
    # A zombie has exited and only awaits reaping; it is not a running process.
    if os.path.isdir("/proc"):
        with contextlib.suppress(OSError):
            with open(f"/proc/{pid}/stat", encoding="latin-1") as fh:
                stat_contents = fh.read()
            rparen = stat_contents.rfind(")")
            if rparen >= 0 and stat_contents[rparen + 2 : rparen + 3] == "Z":
                return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def descendant_pids(pid: int) -> set[int]:
    """Return every live descendant of ``pid`` (excluding ``pid`` itself)."""
    parent_map = _ppid_map()
    children: dict[int, list[int]] = {}
    for child, parent in parent_map.items():
        children.setdefault(parent, []).append(child)

    found: set[int] = set()
    stack = list(children.get(pid, []))
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(children.get(current, []))
    return found


def _wait_gone(pids: set[int], timeout: float) -> None:
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        if not any(is_alive(p) for p in pids):
            return
        time.sleep(0.05)


def _signal_tree_posix(pid: int, extra: set[int], sig: int) -> None:
    with contextlib.suppress(Exception):
        pgid = os.getpgid(pid)
        if pgid == pid:
            os.killpg(pgid, sig)
    with contextlib.suppress(Exception):
        os.kill(pid, sig)
    for p in extra:
        with contextlib.suppress(Exception):
            os.kill(p, sig)


def _terminate_tree_windows(pid: int) -> None:  # pragma: no cover - Windows only
    with contextlib.suppress(Exception):
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
        )


def terminate_process_tree(pid: int, kill_timeout: float = 5.0) -> set[int]:
    """
    Terminate ``pid`` and all of its descendants, escalating from graceful to
    forceful. Returns the set of pids that were still alive afterward (empty on
    success). Callers should log/report a non-empty result.
    """
    if pid <= 0:
        return set()

    targets = descendant_pids(pid) | {pid}

    if _IS_WINDOWS:  # pragma: no cover - Windows only
        _terminate_tree_windows(pid)
        _wait_gone(targets, kill_timeout)
        for survivor in (p for p in targets if is_alive(p)):
            with contextlib.suppress(Exception):
                k32 = ctypes.__dict__["windll"].kernel32
                handle = k32.OpenProcess(_PROCESS_TERMINATE, False, survivor)
                if handle:
                    k32.TerminateProcess(handle, 1)
                    k32.CloseHandle(handle)
        _wait_gone(targets, 1.0)
    else:
        graceful = getattr(__import__("signal"), "SIGTERM", 15)
        forceful = getattr(__import__("signal"), "SIGKILL", 9)
        _signal_tree_posix(pid, targets - {pid}, graceful)
        _wait_gone(targets, kill_timeout)
        remaining = {p for p in targets if is_alive(p)}
        if remaining:
            _signal_tree_posix(pid, remaining - {pid}, forceful)
            _wait_gone(remaining, 1.0)

    survivors = {p for p in targets if is_alive(p)}
    if survivors:
        logging.warning("Process tree %s left surviving descendants: %s", pid, sorted(survivors))
    return survivors


def apply_memory_limit(limit_bytes: int) -> bool:
    """
    Apply a best-effort memory ceiling to the current process.

    POSIX uses ``RLIMIT_AS``; Windows relies on a Job Object instead (see
    :class:`WindowsJob`). Returns ``True`` when a limit was applied.
    """
    if limit_bytes <= 0:
        return False
    if _IS_WINDOWS:
        return False
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_soft = limit_bytes if hard == resource.RLIM_INFINITY else min(limit_bytes, hard)
        if soft != resource.RLIM_INFINITY and soft <= new_soft:
            return True
        resource.setrlimit(resource.RLIMIT_AS, (new_soft, hard))
        return True
    except Exception as exc:
        logging.debug("Could not apply RLIMIT_AS memory limit: %s", exc)
        return False


class WindowsJob:  # pragma: no cover - Windows only
    """
    Windows Job Object that owns a process tree.

    ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` guarantees every descendant is killed
    when the handle is closed, and ``JOB_OBJECT_LIMIT_PROCESS_MEMORY`` enforces a
    per-process memory ceiling.
    """

    _KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_MEMORY = 0x0100
    _EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self, memory_limit_bytes: int | None = None) -> None:
        self._handle: int | None = None
        if not _IS_WINDOWS:
            return
        try:
            import ctypes
            from ctypes import wintypes

            class _IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
                )]

            class _BASIC_LIMIT(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_void_p),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class _EXTENDED_LIMIT(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", _BASIC_LIMIT),
                    ("IoInfo", _IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            k32 = ctypes.__dict__["windll"].kernel32
            k32.CreateJobObjectW.restype = ctypes.c_void_p
            handle = k32.CreateJobObjectW(None, None)
            if not handle:
                return

            info = _EXTENDED_LIMIT()
            info.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
            if memory_limit_bytes and memory_limit_bytes > 0:
                info.BasicLimitInformation.LimitFlags |= self._PROCESS_MEMORY
                info.ProcessMemoryLimit = memory_limit_bytes
            k32.SetInformationJobObject(
                ctypes.c_void_p(handle),
                self._EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            self._handle = handle
        except Exception as exc:
            logging.debug("Could not create Windows Job Object: %s", exc)
            self._handle = None

    @property
    def active(self) -> bool:
        return self._handle is not None

    def assign(self, pid: int) -> bool:
        if self._handle is None:
            return False
        try:
            import ctypes

            k32 = ctypes.__dict__["windll"].kernel32
            process = k32.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
            if not process:
                return False
            try:
                return bool(k32.AssignProcessToJobObject(ctypes.c_void_p(self._handle), process))
            finally:
                k32.CloseHandle(process)
        except Exception as exc:
            logging.debug("Could not assign pid %s to job object: %s", pid, exc)
            return False

    def close(self) -> None:
        if self._handle is None:
            return
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.__dict__["windll"].kernel32.CloseHandle(ctypes.c_void_p(self._handle))
        self._handle = None


def run_with_tree_timeout(
    cmd: list[str],
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """
    Run ``cmd`` in its own process group/session so that a timeout kills the
    *whole* tree it spawns, not just the direct child.
    """
    if _IS_WINDOWS:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            creationflags=(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200) | 0x08000000
            ),
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        terminate_process_tree(proc.pid, kill_timeout=5.0)
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)
        raise TimeoutError(f"Helper process exceeded {timeout}s: {cmd[0] if cmd else cmd}") from None
