from __future__ import annotations

import unittest
from unittest.mock import patch

from tdx_stocks.query import format_bytes, print_rows, validate_table


class QueryHelpersTest(unittest.TestCase):
    def test_validate_table(self) -> None:
        validate_table("raw_daily")
        with self.assertRaises(ValueError):
            validate_table("not_a_table")

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1536), "1.5 KB")

    def test_print_rows_empty(self) -> None:
        with patch("builtins.print") as mocked_print:
            print_rows(["a"], [])
        mocked_print.assert_called_once_with("(no rows)")


if __name__ == "__main__":
    unittest.main()
