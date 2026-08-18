import unittest
from unittest.mock import patch

import pandas as pd

from mcp_trading.market import get_market_snapshot


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        index = pd.date_range("2026-01-01", periods=20, freq="D")
        close = pd.Series(range(100, 120), index=index, dtype=float)
        return pd.DataFrame(
            {
                "Open": close - 1,
                "High": close + 1,
                "Low": close - 2,
                "Close": close,
                "Volume": 1000,
            },
            index=index,
        )


class MarketSnapshotTest(unittest.TestCase):
    @patch("mcp_trading.market.yf.Ticker", FakeTicker)
    def test_snapshot_is_neutral_statistics(self):
        result = get_market_snapshot("aapl", "3mo", "1d")
        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["bars"], 20)
        self.assertEqual(result["last_close"], 119.0)
        self.assertIn("수익 보장", result["note"])

    def test_interval_allowlist(self):
        with self.assertRaises(ValueError):
            get_market_snapshot("AAPL", "3mo", "1m")


if __name__ == "__main__":
    unittest.main()
