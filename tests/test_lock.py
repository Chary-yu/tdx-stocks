from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from time import time
from unittest.mock import patch

from tdx_stocks.exit_codes import LockedError
from tdx_stocks.lock import acquire_database_lock


class LockTest(unittest.TestCase):
    def test_acquire_and_release_removes_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "Database" / ".lock"
            with acquire_database_lock(lock_path, "sync"):
                self.assertTrue(lock_path.exists())
            self.assertFalse(lock_path.exists())

    def test_stale_lock_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "Database" / ".lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "command": "sync",
                        "started_at": "2024-01-01T00:00:00",
                        "token": "stale-token",
                        "process_cmdline": "old process",
                    }
                ),
                encoding="utf-8",
            )
            with patch("tdx_stocks.lock._read_proc_cmdline", return_value="nginx: worker process"):
                with acquire_database_lock(lock_path, "sync"):
                    data = json.loads(lock_path.read_text(encoding="utf-8"))
                    self.assertEqual(data["command"], "sync")
                    self.assertNotEqual(data["token"], "stale-token")
            self.assertFalse(lock_path.exists())

    def test_active_lock_raises_locked_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "Database" / ".lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {
                        "pid": 12345,
                        "command": "sync",
                        "started_at": "2024-01-01T00:00:00",
                        "token": "active-token",
                        "process_cmdline": "tdx-stocks sync",
                    }
                ),
                encoding="utf-8",
            )
            with patch("tdx_stocks.lock._pid_exists", return_value=True), patch(
                "tdx_stocks.lock._read_proc_cmdline",
                return_value="tdx-stocks sync",
            ):
                with self.assertRaises(LockedError) as ctx:
                    with acquire_database_lock(lock_path, "sync"):
                        pass
                self.assertIn("another write task running", str(ctx.exception))

    def test_old_corrupt_lock_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "Database" / ".lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("{not json}", encoding="utf-8")
            old = time() - 3600
            os.utime(lock_path, (old, old))

            with acquire_database_lock(lock_path, "sync"):
                data = json.loads(lock_path.read_text(encoding="utf-8"))
                self.assertEqual(data["command"], "sync")
                self.assertIn("token", data)
            self.assertFalse(lock_path.exists())

    def test_recent_corrupt_lock_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "Database" / ".lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("{not json}", encoding="utf-8")

            with self.assertRaises(LockedError) as ctx:
                with acquire_database_lock(lock_path, "sync"):
                    pass
            self.assertIn("invalid lock file", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
