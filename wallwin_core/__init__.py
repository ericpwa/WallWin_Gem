"""WallWin Gem V3 API-first core package.

The Streamlit V2 app remains the human-facing UI.  This package is the
deterministic quant/API facade that can later be exposed through FastAPI or
Custom GPT Actions.
"""

from .api_layer import (
    analyze_daytrade,
    analyze_long_term,
    analyze_swing,
    backtest_signal,
    export_report,
    health,
    risk_position_size,
    scan_watchlist,
)

__all__ = [
    "health",
    "analyze_long_term",
    "analyze_swing",
    "analyze_daytrade",
    "scan_watchlist",
    "backtest_signal",
    "risk_position_size",
    "export_report",
]
