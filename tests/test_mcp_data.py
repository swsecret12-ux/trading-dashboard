import unittest

from mcp_trading.data import (
    ALLOWED_COLUMNS,
    SupabaseReadClient,
    clamp_limit,
    normalize_filter,
    validate_ticker,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


class DataHelpersTest(unittest.TestCase):
    def test_limit_is_clamped(self):
        self.assertEqual(clamp_limit(-10), 1)
        self.assertEqual(clamp_limit(500), 50)
        self.assertEqual(clamp_limit("bad"), 10)

    def test_ticker_validation(self):
        self.assertEqual(validate_ticker(" aapl "), "AAPL")
        with self.assertRaises(ValueError):
            validate_ticker("AAPL),or=(id.eq.1")

    def test_text_filter_is_normalized_and_bounded(self):
        self.assertEqual(normalize_filter("  win\n  rate  "), "win rate")
        self.assertEqual(len(normalize_filter("x" * 200)), 100)
        self.assertIsNone(normalize_filter(" \t "))

    def test_client_is_get_only_and_uses_fixed_table(self):
        session = FakeSession([{"id": 1, "ticker": "AAPL"}])
        client = SupabaseReadClient(
            "https://example.supabase.co", "public-key", session=session
        )
        rows = client.list_recent_trades(limit=1, ticker="AAPL")
        self.assertEqual(rows[0]["ticker"], "AAPL")
        url, options = session.calls[0]
        self.assertTrue(url.endswith("/rest/v1/trade_history"))
        self.assertEqual(options["params"]["ticker"], "eq.AAPL")
        self.assertNotIn("public-key", str(rows))

    def test_queries_use_explicit_column_allowlists(self):
        session = FakeSession([])
        client = SupabaseReadClient(
            "https://example.supabase.co", "public-key", session=session
        )
        client.get_trade_detail("trade-1")
        client.list_sector_research()

        for url, options in session.calls:
            table = url.rsplit("/", 1)[-1]
            selected = set(options["params"]["select"].split(","))
            self.assertNotIn("*", selected)
            self.assertTrue(selected.issubset(ALLOWED_COLUMNS[table]))

    def test_unknown_table_is_rejected(self):
        client = SupabaseReadClient(
            "https://example.supabase.co", "public-key", session=FakeSession([])
        )
        with self.assertRaises(ValueError):
            client._get("secret_table", {"select": "*"})

    def test_unknown_column_is_rejected(self):
        client = SupabaseReadClient(
            "https://example.supabase.co", "public-key", session=FakeSession([])
        )
        with self.assertRaises(ValueError):
            client._get("trade_history", {"select": "id,private_note"})


if __name__ == "__main__":
    unittest.main()
