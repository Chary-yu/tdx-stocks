from __future__ import annotations

import struct
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tdx_stocks.tdx_day import code_from_path, is_a_share_symbol, read_day_records


class TdxDayTest(unittest.TestCase):
    def test_code_from_path(self) -> None:
        self.assertEqual(code_from_path(Path("sh600000.day")), ("sh", "600000"))
        self.assertEqual(code_from_path(Path("sz000001.day")), ("sz", "000001"))

    def test_a_share_filter(self) -> None:
        self.assertTrue(is_a_share_symbol("sh", "600000"))
        self.assertTrue(is_a_share_symbol("sh", "688001"))
        self.assertTrue(is_a_share_symbol("sz", "000001"))
        self.assertTrue(is_a_share_symbol("sz", "300001"))
        self.assertFalse(is_a_share_symbol("sh", "000001"))
        self.assertFalse(is_a_share_symbol("sz", "399001"))

    def test_read_day_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sh600000.day"
            record = struct.pack(
                "<IIIIIfII",
                20240102,
                101,
                123,
                99,
                111,
                12345.0,
                1000,
                0,
            )
            path.write_bytes(record)

            rows = list(read_day_records(path))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].market, "sh")
        self.assertEqual(rows[0].symbol, "600000")
        self.assertEqual(rows[0].trade_date, date(2024, 1, 2))
        self.assertEqual(rows[0].open, 1.01)
        self.assertEqual(rows[0].high, 1.23)
        self.assertEqual(rows[0].low, 0.99)
        self.assertEqual(rows[0].close, 1.11)
        self.assertEqual(rows[0].amount, 12345.0)
        self.assertEqual(rows[0].volume, 1000)


if __name__ == "__main__":
    unittest.main()
