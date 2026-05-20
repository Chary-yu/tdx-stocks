from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from tdx_stocks import platform_paths


class PlatformPathsTest(unittest.TestCase):
    def test_to_windows_path_converts_wsl_mount_paths(self) -> None:
        self.assertEqual(platform_paths.to_windows_path(Path("/mnt/d/zcyu/report.md")), "D:\\zcyu\\report.md")
        self.assertIsNone(platform_paths.to_windows_path(Path("/tmp/report.md")))

    def test_open_file_uses_explorer_exe_on_wsl(self) -> None:
        with patch("tdx_stocks.platform_paths.is_wsl", return_value=True), patch(
            "tdx_stocks.platform_paths.subprocess.run"
        ) as mocked_run:
            platform_paths.open_file(Path("/mnt/d/zcyu/report.md"))
        mocked_run.assert_called_once()
        self.assertEqual(mocked_run.call_args.args[0][0], "explorer.exe")

    def test_open_file_uses_platform_specific_commands(self) -> None:
        with patch("tdx_stocks.platform_paths.is_wsl", return_value=False), patch(
            "tdx_stocks.platform_paths.platform.system", return_value="Darwin"
        ), patch("tdx_stocks.platform_paths.subprocess.run") as mocked_run:
            platform_paths.open_file(Path("/tmp/report.md"))
        mocked_run.assert_called_once()
        self.assertEqual(mocked_run.call_args.args[0][0], "open")

        with patch("tdx_stocks.platform_paths.is_wsl", return_value=False), patch(
            "tdx_stocks.platform_paths.platform.system", return_value="Linux"
        ), patch("tdx_stocks.platform_paths.subprocess.run") as mocked_run:
            platform_paths.open_file(Path("/tmp/report.md"))
        mocked_run.assert_called_once()
        self.assertEqual(mocked_run.call_args.args[0][0], "xdg-open")

        with patch("tdx_stocks.platform_paths.is_wsl", return_value=False), patch(
            "tdx_stocks.platform_paths.platform.system", return_value="Windows"
        ), patch("tdx_stocks.platform_paths.os.startfile", create=True) as mocked_startfile:
            platform_paths.open_file(Path("C:/tmp/report.md"))
        mocked_startfile.assert_called_once()

    def test_format_report_path_shows_windows_and_wsl_paths(self) -> None:
        text = platform_paths.format_report_path(Path("/mnt/d/zcyu/report.md"))
        self.assertIn("Report:", text)
        self.assertIn("WSL: /mnt/d/zcyu/report.md", text)
        self.assertIn("Windows: D:\\zcyu\\report.md", text)
