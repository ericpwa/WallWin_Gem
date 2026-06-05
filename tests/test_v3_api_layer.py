import unittest

import pandas as pd

from wallwin_core import (
    analyze_daytrade,
    analyze_long_term,
    analyze_swing,
    backtest_signal,
    export_report,
    health,
    risk_position_size,
    scan_watchlist,
)


def synthetic_ohlcv(rows=280, start=50.0):
    dates = pd.date_range("2025-01-02", periods=rows, freq="B")
    values = []
    for idx, day in enumerate(dates):
        close = start + idx * 0.08 + (idx % 7) * 0.03
        open_ = close * 0.995
        high = close * 1.012
        low = close * 0.988
        volume = 1_500_000 + (idx % 20) * 25_000
        values.append({"Date": day.isoformat(), "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})
    return values


def synthetic_intraday(rows=72, start=70.0):
    dates = pd.date_range("2026-06-05 09:00", periods=rows, freq="5min")
    values = []
    for idx, day in enumerate(dates):
        close = start + idx * 0.015
        values.append({"Date": day.isoformat(), "Open": close - 0.03, "High": close + 0.08, "Low": close - 0.08, "Close": close, "Volume": 50_000 + idx * 100})
    return values


class V3ApiLayerTest(unittest.TestCase):
    def test_health(self):
        response = health()
        self.assertEqual(response["status"], "OK")
        self.assertEqual(response["result"]["service"], "WallWin_Gem")

    def test_analyze_swing_with_user_data(self):
        response = analyze_swing(
            {
                "symbol": "2206.TW",
                "ohlcv": synthetic_ohlcv(),
                "info": {"trailingPE": 10.4, "priceToBook": 2.1, "returnOnEquity": 0.13, "marketCap": 90_000_000_000},
                "advanced": {"營收YoY": 8.0, "EPSYoY": 11.0, "ROE": 13.0, "毛利率": 24.0},
            }
        )
        self.assertEqual(response["status"], "OK")
        self.assertIn("input.ohlcv", response["meta"]["source_tags"])
        self.assertIn("wallwin.rule_engine", response["meta"]["source_tags"])
        self.assertGreaterEqual(response["result"]["engine"]["win_score"], 0)
        self.assertLessEqual(response["result"]["engine"]["win_score"], 100)

    def test_analyze_long_term_insufficient_data(self):
        response = analyze_long_term({"symbol": "2206.TW", "ohlcv": synthetic_ohlcv(rows=20)})
        self.assertEqual(response["status"], "DATA_INSUFFICIENT")
        self.assertEqual(response["meta"]["confidence"], "insufficient")

    def test_analyze_daytrade_uses_intraday_payload(self):
        response = analyze_daytrade({"symbol": "2206.TW", "ohlcv": synthetic_ohlcv(), "intraday_ohlcv": synthetic_intraday()})
        self.assertEqual(response["status"], "OK")
        self.assertTrue(response["result"]["daytrade"]["available"])
        self.assertIn("input.intraday_ohlcv", response["meta"]["source_tags"])

    def test_scan_watchlist(self):
        response = scan_watchlist({"symbols": ["2206.TW", "2330.TW"], "market_data": {"2206.TW": synthetic_ohlcv(), "2330.TW": synthetic_ohlcv(start=80)}})
        self.assertEqual(response["status"], "OK")
        self.assertEqual(len(response["result"]["candidates"]), 2)

    def test_backtest_signal(self):
        response = backtest_signal({"symbol": "2206.TW", "ohlcv": synthetic_ohlcv(), "params": {"rvol": 0.5, "max_atr": 10, "hold": 15}})
        self.assertEqual(response["status"], "OK")
        self.assertIn("stats", response["result"])
        self.assertIn("trades", response["result"])

    def test_position_size(self):
        response = risk_position_size({"entry": 60, "stop": 55, "account_size": 1_000_000, "risk_pct": 1, "max_position_pct": 20})
        self.assertEqual(response["status"], "OK")
        self.assertEqual(response["result"]["quantity"], 2000)

    def test_export_report_is_rule_based(self):
        analysis = analyze_swing({"symbol": "2206.TW", "ohlcv": synthetic_ohlcv()})
        response = export_report({"analysis": analysis})
        self.assertEqual(response["status"], "OK")
        self.assertIn("WallWin Gem API Report", response["result"]["content"])
        self.assertIn("不含 AI", response["result"]["content"])


if __name__ == "__main__":
    unittest.main()
