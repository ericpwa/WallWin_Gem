"""FastAPI HTTP layer for WallWin Gem V3 API-first.

Run locally:
    uvicorn api_app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

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


class ApiPayload(BaseModel):
    symbol: str | None = None
    symbols: list[str] | None = None
    ohlcv: list[dict[str, Any]] | None = None
    intraday_ohlcv: list[dict[str, Any]] | None = None
    benchmark_ohlcv: list[dict[str, Any]] | None = None
    market_data: dict[str, list[dict[str, Any]]] | None = None
    info: dict[str, Any] | None = None
    advanced: dict[str, Any] | None = None
    mode: str | None = None
    daytrade_direction: str | None = None
    params: dict[str, Any] | None = None
    fetch: bool = Field(default=False, description="When true, Data Layer may fetch yfinance data.")
    period: str | None = None
    interval: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class RiskPayload(BaseModel):
    entry: float
    stop: float
    account_size: float
    risk_pct: float
    max_position_pct: float | None = None


class ExportPayload(BaseModel):
    analysis: dict[str, Any]


app = FastAPI(
    title="WallWin Gem V3 API",
    version="3.0.0-phase3a",
    description="API-first deterministic quant engine for WallWin Gem. No Google Finance integration.",
)


@app.get("/health")
def http_health() -> dict[str, Any]:
    response = health()
    response["result"]["fastapi_enabled"] = True
    response["result"]["http_layer"] = "FastAPI"
    response["result"]["http_version"] = "3.0.0-phase3a"
    return response


@app.post("/analyze/long-term")
def http_analyze_long_term(payload: ApiPayload) -> dict[str, Any]:
    return analyze_long_term(payload.to_payload())


@app.post("/analyze/swing")
def http_analyze_swing(payload: ApiPayload) -> dict[str, Any]:
    return analyze_swing(payload.to_payload())


@app.post("/analyze/daytrade")
def http_analyze_daytrade(payload: ApiPayload) -> dict[str, Any]:
    return analyze_daytrade(payload.to_payload())


@app.post("/scan/watchlist")
def http_scan_watchlist(payload: ApiPayload) -> dict[str, Any]:
    return scan_watchlist(payload.to_payload())


@app.post("/backtest/signal")
def http_backtest_signal(payload: ApiPayload) -> dict[str, Any]:
    return backtest_signal(payload.to_payload())


@app.post("/risk/position-size")
def http_risk_position_size(payload: RiskPayload) -> dict[str, Any]:
    return risk_position_size(payload.model_dump())


@app.post("/export/report")
def http_export_report(payload: ExportPayload) -> dict[str, Any]:
    return export_report(payload.model_dump())
