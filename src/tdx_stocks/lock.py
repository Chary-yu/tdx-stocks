from __future__ import annotations

import atexit
import json
import os
import signal
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from secrets import token_hex
from typing import Any

from .exit_codes import LockedError


_CORRUPT_LOCK_STALE_SECONDS = 600


@dataclass(frozen=True)
class LockMetadata:
    pid: int
    command: str
    started_at: str
    token: str
    process_cmdline: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "command": self.command,
            "started_at": self.started_at,
            "token": self.token,
            "process_cmdline": self.process_cmdline,
        }


class AcquireLock(AbstractContextManager["AcquireLock"]):
    def __init__(self, lock_path: Path, command: str) -> None:
        self.lock_path = lock_path
        self.command = command
        self._metadata: LockMetadata | None = None
        self._active = False
        self._registered_atexit = False
        self._signal_handlers: dict[int, Any] = {}

    def __enter__(self) -> "AcquireLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False

    def acquire(self) -> None:
        if self._active:
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        while True:
            existing = _read_lock_metadata(self.lock_path)
            if existing is not None:
                if _is_stale_lock(existing):
                    _remove_if_stale(self.lock_path, existing)
                    continue
                raise LockedError(
                    f"detected another write task running (PID: {existing.pid})"
                )
            if self.lock_path.exists():
                if _is_old_corrupt_lock(self.lock_path):
                    try:
                        self.lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise LockedError(f"detected invalid lock file: {self.lock_path}")

            metadata = LockMetadata(
                pid=os.getpid(),
                command=self.command,
                started_at=datetime.now().isoformat(timespec="seconds"),
                token=token_hex(16),
                process_cmdline=_current_process_cmdline(),
            )
            try:
                fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
            except FileExistsError:
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(metadata.to_dict(), handle, ensure_ascii=True, indent=2)
                handle.write("\n")

            self._metadata = metadata
            self._active = True
            self._register_cleanup()
            return

    def release(self) -> None:
        if not self._active:
            return
        metadata = self._metadata
        self._active = False
        self._metadata = None
        self._unregister_cleanup()
        if metadata is None:
            return
        current = _read_lock_metadata(self.lock_path)
        if current is None or current.token != metadata.token:
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def _register_cleanup(self) -> None:
        if not self._registered_atexit:
            atexit.register(self.release)
            self._registered_atexit = True
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            self._signal_handlers[signum] = previous

            def _handler(received_signum: int, frame, *, _signum=signum, _previous=previous) -> None:  # noqa: ANN001
                self.release()
                if callable(_previous):
                    _previous(received_signum, frame)
                    return
                if _signum == signal.SIGINT:
                    raise KeyboardInterrupt
                raise SystemExit(128 + _signum)

            signal.signal(signum, _handler)

    def _unregister_cleanup(self) -> None:
        if self._registered_atexit:
            try:
                atexit.unregister(self.release)
            except AttributeError:  # pragma: no cover - Python < 3.9 fallback
                pass
            self._registered_atexit = False
        for signum, previous in self._signal_handlers.items():
            try:
                signal.signal(signum, previous)
            except (ValueError, OSError):  # pragma: no cover - signal not available
                pass
        self._signal_handlers.clear()


def acquire_database_lock(lock_path: Path, command: str) -> AcquireLock:
    return AcquireLock(lock_path, command)


def _read_lock_metadata(path: Path) -> LockMetadata | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    try:
        return LockMetadata(
            pid=int(data["pid"]),
            command=str(data.get("command", "")),
            started_at=str(data.get("started_at", "")),
            token=str(data["token"]),
            process_cmdline=str(data.get("process_cmdline", "")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _remove_if_stale(path: Path, metadata: LockMetadata) -> None:
    if _is_stale_lock(metadata):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _is_old_corrupt_lock(path: Path) -> bool:
    try:
        age_seconds = datetime.now().timestamp() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds >= _CORRUPT_LOCK_STALE_SECONDS


def _is_stale_lock(metadata: LockMetadata) -> bool:
    if not _pid_exists(metadata.pid):
        return True
    if os.name == "posix":
        cmdline = _read_proc_cmdline(metadata.pid)
        if cmdline is None:
            return False
        lowered = cmdline.lower()
        if "tdx-stocks" not in lowered and "tdx_stocks" not in lowered:
            return True
    return False


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_proc_cmdline(pid: int) -> str | None:
    proc_path = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = proc_path.read_bytes()
    except OSError:
        return None
    if not raw:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()


def _current_process_cmdline() -> str:
    return " ".join(sys.argv).strip()
