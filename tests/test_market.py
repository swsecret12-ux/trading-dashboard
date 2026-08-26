import unittest
from unittest.mock import patch

import pandas as pd

from mcp_trading.market import get_chart_analysis_context, get_market_snapshot


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, **kwargs):
        index = pd.date_range("2026-01-01", periods=80, freq="D")
        close = pd.Series(range(100, 180), index=index, dtype=float)
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
        self.assertEqual(result["bars"], 80)
        self.assertEqual(result["last_close"], 179.0)
        self.assertIn("수익 보장", result["note"])

    @patch("mcp_trading.market.yf.Ticker", FakeTicker)
    def test_chart_context_contains_neutral_cross_check_data(self):
        result = get_chart_analysis_context("aapl", "6mo", "1d", recent_bars=12)

        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(len(result["recent_bars"]), 12)
        self.assertEqual(result["trend"]["state"], "상승 정렬")
        self.assertIsNotNone(result["momentum"]["macd_histogram"])
        self.assertIsNotNone(result["volatility"]["atr14"])
        self.assertEqual(result["volume"]["latest_to_average20_ratio"], 1.0)
        self.assertEqual(result["reference_levels"]["window_bars"], 20)
        self.assertIn("직접", result["usage_note"])

    @patch("mcp_trading.market.yf.Ticker", FakeTicker)
    def test_chart_context_limits_returned_bars(self):
        with self.assertRaises(ValueError):
            get_chart_analysis_context("AAPL", recent_bars=61)

        with self.assertRaises(ValueError):
            get_chart_analysis_context("AAPL", recent_bars=True)

    def test_interval_allowlist(self):
        with self.assertRaises(ValueError):
            get_market_snapshot("AAPL", "3mo", "1m")


if __name__ == "__main__":
    unittest.main()
