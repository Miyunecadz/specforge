"""Locking and atomic writes for run files (BUILD_SPEC §5, Concurrent writes).

Locks are lock files created with O_CREAT | O_EXCL, never fcntl/flock, because those are
unreliable on some mounted filesystems. Whole-file replacement always goes through a
temporary file in the same directory followed by os.replace. Stdlib only, so hooks can
import it.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

LOCK_SUFFIX = ".lock"
DEFAULT_LOCK_TIMEOUT = 30.0
DEFAULT_STALE_AFTER = 30.0


class LockTimeout(RuntimeError):
    pass


def lock_path(target: Path | str) -> Path:
    return Path(str(target) + LOCK_SUFFIX)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_is_stale(path: Path, stale_after: float) -> bool:
    """A lock is stale when its holder process is gone, or it is older than stale_after.

    Run-file operations take milliseconds, so a lock older than stale_after seconds is
    assumed abandoned.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    try:
        info = json.loads(raw)
    except ValueError:
        # Holder may still be writing its details; judge by age only.
        return age > stale_after
    if info.get("host") == socket.gethostname() and isinstance(info.get("pid"), int):
        if not _pid_alive(info["pid"]):
            return True
    return age > stale_after


@contextmanager
def file_lock(
    target: Path | str,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
    stale_after: float = DEFAULT_STALE_AFTER,
) -> Iterator[None]:
    path = lock_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if _lock_is_stale(path, stale_after):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() > deadline:
                raise LockTimeout(f"could not acquire {path} within {timeout}s")
            time.sleep(0.002)
            continue
        try:
            os.write(
                fd,
                json.dumps(
                    {"pid": os.getpid(), "host": socket.gethostname(), "t": time.time()}
                ).encode(),
            )
        finally:
            os.close(fd)
        break
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Replace path with data via a temp file in the same directory and os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    _fsync_dir(path.parent)


def dumps_json(obj: object) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def atomic_write_json(path: Path | str, obj: object) -> bytes:
    data = dumps_json(obj).encode("utf-8")
    atomic_write_bytes(path, data)
    return data


def locked_atomic_write_json(path: Path | str, obj: object) -> bytes:
    with file_lock(path):
        return atomic_write_json(path, obj)


def append_line_unlocked(path: Path | str, line: str) -> None:
    """Append one line. Caller must hold the file's lock."""
    if "\n" in line:
        raise ValueError("a JSONL line must not contain a newline")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def append_line(path: Path | str, line: str) -> None:
    with file_lock(path):
        append_line_unlocked(path, line)


def read_json(path: Path | str) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
