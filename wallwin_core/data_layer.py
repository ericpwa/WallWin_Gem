"""Data access helpers for WallWin Gem V3.

No Google Finance integration is used here by design.  The current data stack is
yfinance plus explicit user/HITL inputs.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .schemas import (
    SOURCE_YFINANCE,
    STATUS_DATA_SOURCE_ERROR,
    STATUS_DATA_SOURCE_RATE_LIMIT,
    STATUS_OK,
)


def normalize_symbol(raw_symbol: str) -> str:
    symbol = str(raw_symbol or "").strip().upper()
    if symbol.isdigit():
        return f"{symbol}.TW"
    return symbol


def is_rate_limit_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "ratelimit" in text or "rate limit" in text or "resource_exhausted" in text or "too many requests" in text


def fetch_yfinance_history(symbol: str, period: str = "1y", interval: str = "1d") -> dict[str, Any]:
    try:
        import yfinance as yf

        normalized = normalize_symbol(symbol)
        data = yf.Ticker(normalized).history(period=period, interval=interval)
        if data is None or data.empty:
            return {"status": STATUS_DATA_SOURCE_ERROR, "data": pd.DataFrame(), "source_tag": SOURCE_YFINANCE, "error": "empty yfinance history"}
        return {"status": STATUS_OK, "data": data, "source_tag": SOURCE_YFINANCE, "error": None}
    except Exception as exc:
        return {
            "status": STATUS_DATA_SOURCE_RATE_LIMIT if is_rate_limit_error(exc) else STATUS_DATA_SOURCE_ERROR,
            "data": pd.DataFrame(),
            "source_tag": SOURCE_YFINANCE,
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_yfinance_info(symbol: str) -> dict[str, Any]:
    try:
        import yfinance as yf

        normalized = normalize_symbol(symbol)
        return {"status": STATUS_OK, "data": yf.Ticker(normalized).info or {}, "source_tag": SOURCE_YFINANCE, "error": None}
    except Exception as exc:
        return {
            "status": STATUS_DATA_SOURCE_RATE_LIMIT if is_rate_limit_error(exc) else STATUS_DATA_SOURCE_ERROR,
            "data": {},
            "source_tag": SOURCE_YFINANCE,
            "error": f"{type(exc).__name__}: {exc}",
        }
