"""Functional API-first facade for WallWin Gem V3.

Phase 1 deliberately exposes plain Python callables.  They can be wrapped by
FastAPI or Custom GPT Actions later without changing the quant calculations.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from . import data_layer
from .quant_engine import (
    calculate_daytrade_matrix,
    calculate_position_size,
    data_confidence,
    get_light,
    normalize_ohlcv,
    run_signal_backtest,
    score_multifactor,
    build_trade_plan,
)
from .schemas import (
    API_VERSION,
    ApiError,
    ApiMeta,
    SOURCE_HITL,
    SOURCE_RULE_ENGINE,
    SOURCE_SYNTHETIC_OR_USER,
    SOURCE_YFINANCE,
    STATUS_DATA_INSUFFICIENT,
    STATUS_DATA_SOURCE_ERROR,
    STATUS_DATA_SOURCE_RATE_LIMIT,
    STATUS_OK,
    STATUS_VALIDATION_ERROR,
    api_response,
)


def health() -> dict[str, Any]:
    return api_response(
        "/health",
        {"service": "WallWin_Gem", "version": API_VERSION, "mode": "api-first-phase1", "fastapi_enabled": False},
        ApiMeta(status=STATUS_OK, confidence="high", source_tags=[SOURCE_RULE_ENGINE]),
    )


def _load_ohlcv(payload: dict[str, Any], default_period: str = "1y", default_interval: str = "1d") -> tuple[pd.DataFrame, ApiMeta]:
    meta = ApiMeta(status=STATUS_OK, confidence="medium", source_tags=[SOURCE_RULE_ENGINE])
    if payload.get("ohlcv") is not None:
        try:
            df = normalize_ohlcv(payload["ohlcv"])
            meta.source_tags.append(SOURCE_SYNTHETIC_OR_USER)
            meta.confidence = data_confidence(len(df))
            return df, meta
        except Exception as exc:
            meta.status = STATUS_VALIDATION_ERROR
            meta.confidence = "insufficient"
            meta.errors.append(ApiError("INVALID_OHLCV", str(exc), "ohlcv"))
            return pd.DataFrame(), meta
    if payload.get("fetch") is True:
        data = data_layer.fetch_yfinance_history(payload.get("symbol", ""), payload.get("period", default_period), payload.get("interval", default_interval))
        meta.source_tags.append(SOURCE_YFINANCE)
        if data["status"] != STATUS_OK:
            meta.status = data["status"]
            meta.confidence = "insufficient"
            meta.errors.append(ApiError(data["status"], data.get("error") or "data source failed", "symbol"))
            return pd.DataFrame(), meta
        df = normalize_ohlcv(data["data"])
        meta.confidence = data_confidence(len(df))
        return df, meta
    meta.status = STATUS_DATA_INSUFFICIENT
    meta.confidence = "insufficient"
    meta.insufficient_data.append("ohlcv is required unless fetch=true")
    return pd.DataFrame(), meta


def _fetch_info_if_needed(payload: dict[str, Any], meta: ApiMeta) -> dict[str, Any]:
    info = payload.get("info") or {}
    if info:
        meta.source_tags.append("input.info")
        return info
    if payload.get("fetch") is True:
        data = data_layer.fetch_yfinance_info(payload.get("symbol", ""))
        if SOURCE_YFINANCE not in meta.source_tags:
            meta.source_tags.append(SOURCE_YFINANCE)
        if data["status"] != STATUS_OK:
            meta.warnings.append(data.get("error") or "info data source failed")
            return {}
        return data["data"]
    return {}


def _analysis(endpoint: str, payload: dict[str, Any], style: str, default_mode: str, default_period: str = "1y", default_interval: str = "1d") -> dict[str, Any]:
    payload = payload or {}
    symbol = payload.get("symbol", "")
    if not symbol:
        return api_response(endpoint, None, ApiMeta(status=STATUS_VALIDATION_ERROR, confidence="insufficient", source_tags=[SOURCE_RULE_ENGINE], errors=[ApiError("REQUIRED", "symbol is required", "symbol")]), {})
    hist, meta = _load_ohlcv(payload, default_period, default_interval)
    if meta.status != STATUS_OK:
        return api_response(endpoint, None, meta, {"symbol": symbol, "style": style})
    if len(hist) < 60:
        meta.status = STATUS_DATA_INSUFFICIENT
        meta.confidence = "insufficient"
        meta.insufficient_data.append(f"analysis requires at least 60 OHLCV rows; got {len(hist)}")
        return api_response(endpoint, None, meta, {"symbol": symbol, "style": style})
    info = _fetch_info_if_needed(payload, meta)
    advanced = payload.get("advanced") or {}
    if advanced:
        meta.source_tags.append(SOURCE_HITL)
    benchmark = None
    if payload.get("benchmark_ohlcv") is not None:
        try:
            benchmark = normalize_ohlcv(payload["benchmark_ohlcv"])
            meta.source_tags.append("input.benchmark_ohlcv")
        except Exception as exc:
            meta.warnings.append(f"benchmark ignored: {exc}")
    mode = payload.get("mode") or default_mode
    try:
        engine = score_multifactor(symbol, info, hist, advanced, style, mode, benchmark)
        daytrade = None
        if style == "當沖":
            intraday_payload = payload.get("intraday_ohlcv")
            if intraday_payload is not None:
                daytrade = calculate_daytrade_matrix(normalize_ohlcv(intraday_payload))
                meta.source_tags.append("input.intraday_ohlcv")
        light, advice = get_light(engine, daytrade, payload.get("daytrade_direction", "做多"))
        trade_plan = build_trade_plan(engine, daytrade, payload.get("daytrade_direction", "做多"))
        result = {"symbol": symbol, "style": style, "mode": mode, "light": light, "advice": advice, "engine": engine, "daytrade": daytrade, "trade_plan": trade_plan}
        return api_response(endpoint, result, meta, {"symbol": symbol, "style": style, "mode": mode})
    except Exception as exc:
        meta.status = STATUS_VALIDATION_ERROR
        meta.confidence = "insufficient"
        meta.errors.append(ApiError("ANALYSIS_FAILED", str(exc)))
        return api_response(endpoint, None, meta, {"symbol": symbol, "style": style, "mode": mode})


def analyze_long_term(payload: dict[str, Any]) -> dict[str, Any]:
    return _analysis("/analyze/long-term", payload, "投資", "白馬模式", "5y", "1d")


def analyze_swing(payload: dict[str, Any]) -> dict[str, Any]:
    return _analysis("/analyze/swing", payload, "波段", "黑馬模式", "2y", "1d")


def analyze_daytrade(payload: dict[str, Any]) -> dict[str, Any]:
    return _analysis("/analyze/daytrade", payload, "當沖", "黑馬模式", "1y", "1d")


def scan_watchlist(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload or {}
    symbols = payload.get("symbols") or []
    if not symbols:
        return api_response("/scan/watchlist", None, ApiMeta(status=STATUS_VALIDATION_ERROR, confidence="insufficient", source_tags=[SOURCE_RULE_ENGINE], errors=[ApiError("REQUIRED", "symbols is required", "symbols")]), {})
    market_data = payload.get("market_data") or {}
    rows = []
    warnings = []
    for symbol in symbols[:50]:
        item_payload = {**payload, "symbol": symbol, "ohlcv": market_data.get(symbol)}
        response = analyze_swing(item_payload)
        if response["status"] == STATUS_OK:
            engine = response["result"]["engine"]
            rows.append({"symbol": symbol, "win_score": engine["win_score"], "bucket": engine["bucket"], "light": response["result"]["light"], "mode": engine["mode"], "hard_flags": engine["hard_flags"]})
        else:
            warnings.append({"symbol": symbol, "status": response["status"], "errors": response["meta"].get("errors", []), "insufficient_data": response["meta"].get("insufficient_data", [])})
    rows = sorted(rows, key=lambda row: row["win_score"], reverse=True)
    status = STATUS_OK if rows else STATUS_DATA_INSUFFICIENT
    meta = ApiMeta(status=status, confidence="medium" if rows else "insufficient", source_tags=[SOURCE_RULE_ENGINE, SOURCE_SYNTHETIC_OR_USER], warnings=[str(w) for w in warnings])
    return api_response("/scan/watchlist", {"candidates": rows, "rejected_or_unscored": warnings}, meta, {"symbol_count": len(symbols)})


def backtest_signal(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload or {}
    hist, meta = _load_ohlcv(payload)
    if meta.status != STATUS_OK:
        return api_response("/backtest/signal", None, meta, {})
    if len(hist) < 120:
        meta.status = STATUS_DATA_INSUFFICIENT
        meta.confidence = "insufficient"
        meta.insufficient_data.append(f"backtest requires at least 120 OHLCV rows; got {len(hist)}")
        return api_response("/backtest/signal", None, meta, {})
    trades, stats = run_signal_backtest(hist, payload.get("params") or {})
    result = {"stats": stats, "trades": trades.to_dict(orient="records")}
    return api_response("/backtest/signal", result, meta, {"symbol": payload.get("symbol"), "params": payload.get("params") or {}})


def risk_position_size(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        result = calculate_position_size(payload.get("entry"), payload.get("stop"), payload.get("account_size"), payload.get("risk_pct"), payload.get("max_position_pct"))
        return api_response("/risk/position-size", result, ApiMeta(status=STATUS_OK, confidence="high", source_tags=[SOURCE_RULE_ENGINE]), {"entry": payload.get("entry"), "stop": payload.get("stop")})
    except Exception as exc:
        return api_response("/risk/position-size", None, ApiMeta(status=STATUS_VALIDATION_ERROR, confidence="insufficient", source_tags=[SOURCE_RULE_ENGINE], errors=[ApiError("POSITION_SIZE_FAILED", str(exc))]), payload or {})


def export_report(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis") if payload else None
    if not analysis or analysis.get("status") != STATUS_OK:
        return api_response("/export/report", None, ApiMeta(status=STATUS_VALIDATION_ERROR, confidence="insufficient", source_tags=[SOURCE_RULE_ENGINE], errors=[ApiError("REQUIRED", "analysis response with status OK is required", "analysis")]), {})
    result = analysis["result"]
    engine = result["engine"]
    plan = result["trade_plan"]
    markdown = "\n".join(
        [
            f"# WallWin Gem API Report - {engine['symbol']}",
            "",
            f"- 週期/模式：{engine['style']} / {engine['mode']}",
            f"- 燈號：{result['light']}，{result['advice']}",
            f"- 勝率分數：{engine['win_score']} / 100 ({engine['bucket']})",
            f"- 白馬分：{engine['white_score']}；黑馬分：{engine['black_score']}",
            f"- 進場：{plan['entry']:.2f}；停損：{plan['stop']:.2f}；目標一：{plan['target_1']:.2f}；目標二：{plan['target_2']:.2f}",
            "",
            "## 因子分數",
            *[f"- {key}: {value:.1f}" for key, value in engine["factor_scores"].items()],
            "",
            "本報告由明確規則與量化計算產生，不含 AI 生成之投資建議。",
        ]
    )
    return api_response("/export/report", {"format": "markdown", "content": markdown}, ApiMeta(status=STATUS_OK, confidence=analysis["meta"].get("confidence", "medium"), source_tags=[SOURCE_RULE_ENGINE]), {"symbol": engine["symbol"]})
