"""Deterministic quant calculations for WallWin Gem V3.

This module intentionally performs no network calls and no LLM calls.  Every
score, light, risk number, and backtest result is derived from explicit inputs.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

STYLE_MODE_PRESETS = {
    ("投資", "白馬模式"): {"min_volume": 200_000, "max_atr": 5.0, "stop": 15.0, "target": 28.0},
    ("投資", "黑馬模式"): {"min_volume": 500_000, "max_atr": 7.0, "stop": 12.0, "target": 35.0},
    ("波段", "白馬模式"): {"min_volume": 300_000, "max_atr": 4.5, "stop": 9.0, "target": 18.0},
    ("波段", "黑馬模式"): {"min_volume": 800_000, "max_atr": 6.0, "stop": 8.0, "target": 24.0},
    ("當沖", "白馬模式"): {"min_volume": 1_000_000, "max_atr": 3.5, "stop": 2.2, "target": 4.0},
    ("當沖", "黑馬模式"): {"min_volume": 1_500_000, "max_atr": 4.5, "stop": 2.8, "target": 5.5},
}

WEIGHTS = {
    "白馬模式": {
        "投資": {"value": 0.18, "growth": 0.13, "quality": 0.22, "momentum": 0.08, "low_vol": 0.10, "liquidity": 0.07, "risk": 0.12, "dividend_safety": 0.10},
        "波段": {"value": 0.12, "growth": 0.12, "quality": 0.18, "momentum": 0.18, "low_vol": 0.12, "liquidity": 0.10, "risk": 0.12, "dividend_safety": 0.06},
        "當沖": {"value": 0.04, "growth": 0.06, "quality": 0.10, "momentum": 0.30, "low_vol": 0.12, "liquidity": 0.18, "risk": 0.18, "dividend_safety": 0.02},
    },
    "黑馬模式": {
        "投資": {"value": 0.08, "growth": 0.20, "quality": 0.12, "momentum": 0.22, "low_vol": 0.08, "liquidity": 0.12, "risk": 0.12, "dividend_safety": 0.06},
        "波段": {"value": 0.05, "growth": 0.16, "quality": 0.08, "momentum": 0.34, "low_vol": 0.08, "liquidity": 0.16, "risk": 0.11, "dividend_safety": 0.02},
        "當沖": {"value": 0.02, "growth": 0.06, "quality": 0.04, "momentum": 0.42, "low_vol": 0.08, "liquidity": 0.24, "risk": 0.13, "dividend_safety": 0.01},
    },
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, safe_float(value)))


def pct_change(current: float, previous: float) -> float:
    previous = safe_float(previous)
    return (safe_float(current) - previous) / previous * 100 if previous else 0.0


def score_bucket(score: float) -> str:
    score = safe_float(score)
    if score >= 78:
        return "A"
    if score >= 62:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def score_high(value: float, weak: float, strong: float) -> float:
    if strong == weak:
        return 50.0
    return clamp((safe_float(value) - weak) / (strong - weak) * 100)


def score_low(value: float, strong: float, weak: float) -> float:
    if not value:
        return 45.0
    if weak == strong:
        return 50.0
    return clamp((weak - safe_float(value)) / (weak - strong) * 100)


def score_range(value: float, low: float, high: float, edge_penalty: float = 0.6) -> float:
    value = safe_float(value)
    if low <= value <= high:
        return 100.0
    gap = low - value if value < low else value - high
    return clamp(100 - gap * 100 * edge_penalty / max(high - low, 1))


def normalize_ohlcv(records_or_df: Any) -> pd.DataFrame:
    df = records_or_df.copy() if isinstance(records_or_df, pd.DataFrame) else pd.DataFrame(records_or_df or [])
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).set_index("Date")
    rename_map = {c.lower(): c for c in OHLCV_COLUMNS}
    df = df.rename(columns={col: rename_map.get(str(col).lower(), col) for col in df.columns})
    missing = [col for col in OHLCV_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns: {', '.join(missing)}")
    df = df[OHLCV_COLUMNS].apply(pd.to_numeric, errors="coerce").dropna()
    return df.sort_index()


def data_confidence(row_count: int) -> str:
    if row_count >= 252:
        return "high"
    if row_count >= 120:
        return "medium"
    if row_count >= 60:
        return "low"
    return "insufficient"


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, float("nan"))
    return (100 - (100 / (1 + rs))).fillna(50)


def atr_pct(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window).mean() / close * 100


def macd_diff(close: pd.Series) -> pd.Series:
    macd = ema(close, 12) - ema(close, 26)
    return macd - ema(macd, 9)


def build_technical_pack(hist: pd.DataFrame, benchmark_hist: pd.DataFrame | None = None) -> dict[str, Any]:
    df = normalize_ohlcv(hist)
    if len(df) < 60:
        raise ValueError("technical pack requires at least 60 OHLCV rows")
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    price = safe_float(close.iloc[-1])
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    atr_series = atr_pct(high, low, close)
    rsi_series = rsi(close)
    macd_series = macd_diff(close)
    adx_proxy = (ma20.diff().abs() / close * 100).rolling(14).mean() * 10
    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_width_series = ((bb_mid + 2 * bb_std) - (bb_mid - 2 * bb_std)) / close * 100
    bb_valid = bb_width_series.dropna()
    bb_width_rank = bb_valid.rank(pct=True).iloc[-1] * 100 if len(bb_valid) else 50
    vol20 = volume.rolling(20).mean()
    rvol = safe_float(volume.iloc[-1]) / safe_float(vol20.iloc[-1], 1)
    typical = (high + low + close) / 3
    vwap = safe_float((typical * volume).rolling(20).sum().iloc[-1] / volume.rolling(20).sum().iloc[-1])
    low_min_20 = safe_float(low.tail(20).min())
    vcp = ((safe_float(high.tail(20).max()) - low_min_20) / low_min_20 * 100) if low_min_20 > 0 else 0
    high_52w = safe_float(high.tail(252).max())
    returns = {label: pct_change(price, safe_float(close.iloc[-days])) if len(close) > days else 0 for label, days in {"1m": 21, "3m": 63, "6m": 126}.items()}
    benchmark_returns = {"1m": 0.0, "3m": 0.0, "6m": 0.0}
    if benchmark_hist is not None:
        try:
            b_df = normalize_ohlcv(benchmark_hist)
            b_close = b_df["Close"]
            b_price = safe_float(b_close.iloc[-1])
            benchmark_returns = {label: pct_change(b_price, safe_float(b_close.iloc[-days])) if len(b_close) > days else 0 for label, days in {"1m": 21, "3m": 63, "6m": 126}.items()}
        except Exception:
            benchmark_returns = {"1m": 0.0, "3m": 0.0, "6m": 0.0}
    rel_strength = sum(returns[k] - benchmark_returns[k] for k in returns) / 3
    breakout_ref = safe_float(high.tail(25).iloc[:-5].max()) if len(high) >= 25 else safe_float(high.tail(20).max())
    return {
        "price": price,
        "volume": safe_float(volume.iloc[-1]),
        "dollar_volume": price * safe_float(volume.iloc[-1]),
        "ma20": safe_float(ma20.iloc[-1]),
        "ma50": safe_float(ma50.iloc[-1]),
        "ma200": safe_float(ma200.iloc[-1]),
        "ma50_slope": pct_change(safe_float(ma50.iloc[-1]), safe_float(ma50.iloc[-21])) if len(ma50.dropna()) > 21 else 0,
        "ma200_slope": pct_change(safe_float(ma200.iloc[-1]), safe_float(ma200.iloc[-21])) if len(ma200.dropna()) > 21 else 0,
        "rvol": rvol,
        "vcp": vcp,
        "vwap": vwap,
        "atr_pct": safe_float(atr_series.iloc[-1]),
        "rsi": safe_float(rsi_series.iloc[-1], 50),
        "macd_diff": safe_float(macd_series.iloc[-1]),
        "adx": safe_float(adx_proxy.iloc[-1]),
        "bb_width": safe_float(bb_width_series.iloc[-1]),
        "bb_width_rank": safe_float(bb_width_rank),
        "dist_52w_high": pct_change(price, high_52w),
        "rel_strength": rel_strength,
        "return_1m": returns["1m"],
        "return_3m": returns["3m"],
        "return_6m": returns["6m"],
        "close_above_breakout_days": int(close.tail(5).gt(breakout_ref).sum()),
        "upper_shadow": (safe_float(high.iloc[-1]) - max(price, safe_float(df["Open"].iloc[-1]))) / price * 100 if price else 0,
        "gap_pct": pct_change(safe_float(df["Open"].iloc[-1]), safe_float(close.iloc[-2])) if len(df) > 2 else 0,
        "data_points": len(df),
    }


def metric_value(info: dict[str, Any] | None, advanced: dict[str, Any] | None, key: str, alt_keys: list[str] | None = None, default: float = 0.0, pct: bool = False) -> float:
    info = info or {}
    advanced = advanced or {}
    for candidate in [key] + (alt_keys or []):
        if candidate in advanced and advanced[candidate] not in ("", None):
            value = safe_float(advanced[candidate], default)
            return value * 100 if pct and abs(value) < 1 else value
        if candidate in info and info[candidate] not in ("", None):
            value = safe_float(info[candidate], default)
            return value * 100 if pct and abs(value) < 1 else value
    return default


def score_multifactor(symbol: str, info: dict[str, Any] | None, hist: pd.DataFrame, advanced: dict[str, Any] | None, style: str, mode: str, benchmark_hist: pd.DataFrame | None = None) -> dict[str, Any]:
    if (style, mode) not in STYLE_MODE_PRESETS:
        raise ValueError(f"unsupported style/mode: {style}/{mode}")
    t = build_technical_pack(hist, benchmark_hist)
    revenue_growth = metric_value(info, advanced, "revenueGrowth", ["營收YoY", "revenue_yoy"], pct=True)
    earnings_growth = metric_value(info, advanced, "earningsGrowth", ["EPSYoY", "eps_yoy"], pct=True)
    roe = metric_value(info, advanced, "returnOnEquity", ["ROE"], pct=True)
    roa = metric_value(info, advanced, "returnOnAssets", ["ROA"], pct=True)
    roic = metric_value(info, advanced, "ROIC", ["roic"], pct=True)
    gross_margin = metric_value(info, advanced, "grossMargins", ["毛利率", "gross_margin"], pct=True)
    op_margin = metric_value(info, advanced, "operatingMargins", ["營益率", "operating_margin"], pct=True)
    net_margin = metric_value(info, advanced, "profitMargins", ["淨利率", "net_margin"], pct=True)
    debt_to_equity = metric_value(info, advanced, "debtToEquity", ["DebtEquity", "負債權益比"])
    current_ratio = metric_value(info, advanced, "currentRatio", ["流動比率"])
    interest_coverage = metric_value(info, advanced, "interestCoverage", ["利息保障倍數"])
    pe = metric_value(info, advanced, "trailingPE", ["PE"])
    pb = metric_value(info, advanced, "priceToBook", ["PB"])
    ps = metric_value(info, advanced, "priceToSalesTrailing12Months", ["PS"])
    ev_ebitda = metric_value(info, advanced, "enterpriseToEbitda", ["EV_EBITDA"])
    dividend_yield = metric_value(info, advanced, "dividendYield", ["殖利率"], pct=True)
    payout_ratio = metric_value(info, advanced, "payoutRatio", ["配息率"], pct=True)
    fcf = metric_value(info, advanced, "freeCashflow", ["自由現金流", "FCF"])
    ocf = metric_value(info, advanced, "operatingCashflow", ["營業現金流", "OCF"])
    market_cap = metric_value(info, advanced, "marketCap", ["市值"])
    fcf_yield = fcf / market_cap * 100 if market_cap > 0 else metric_value(info, advanced, "FCF殖利率", ["fcf_yield"])
    eps_revision = metric_value(info, advanced, "分析師上修", ["analyst_revision", "earnings_revision"])
    pe_percentile = metric_value(info, advanced, "PE分位", ["pe_percentile"], 50)
    pb_percentile = metric_value(info, advanced, "PB分位", ["pb_percentile"], 50)
    value_score = score_low(pe, 10, 35) * 0.22 + score_low(pb, 1.0, 5.0) * 0.18 + score_low(ps, 1.0, 8.0) * 0.12 + score_low(ev_ebitda, 6, 25) * 0.12 + score_high(fcf_yield, 0, 8) * 0.16 + score_low(pe_percentile, 20, 80) * 0.10 + score_low(pb_percentile, 20, 80) * 0.10
    growth_score = score_high(revenue_growth, -5, 30) * 0.30 + score_high(earnings_growth, -10, 35) * 0.35 + score_high(eps_revision, -10, 20) * 0.20 + score_high(t["return_6m"], -15, 35) * 0.15
    quality_score = score_high(roe, 5, 25) * 0.20 + score_high(roa, 2, 12) * 0.12 + score_high(roic, 5, 20) * 0.13 + score_high(gross_margin, 15, 55) * 0.15 + score_high(op_margin, 5, 25) * 0.15 + score_high(net_margin, 3, 20) * 0.10 + score_high(ocf, 0, max(abs(fcf), 1)) * 0.05 + score_low(debt_to_equity, 40, 180) * 0.10
    momentum_score = score_high(t["rel_strength"], -10, 25) * 0.18 + score_high(t["ma50_slope"], -5, 12) * 0.12 + score_high(t["ma200_slope"], -5, 10) * 0.10 + score_range(t["rsi"], 45, 72, 2.0) * 0.12 + (100 if t["macd_diff"] > 0 else 30) * 0.10 + score_high(t["adx"], 12, 35) * 0.10 + score_high(t["rvol"], 0.8, 2.5) * 0.12 + score_low(abs(t["dist_52w_high"]), 0, 35) * 0.08 + score_low(t["vcp"], 4, 18) * 0.08 + score_high(t["close_above_breakout_days"], 0, 4) * 0.10
    low_vol_score = score_low(t["atr_pct"], 2.5, 9.0) * 0.40 + score_low(t["bb_width_rank"], 20, 90) * 0.30 + score_low(abs(t["gap_pct"]), 0.5, 6.0) * 0.30
    liquidity_score = score_high(t["volume"] / 1000, 100, 5000) * 0.35 + score_high(t["dollar_volume"], 50_000_000, 2_000_000_000) * 0.45 + score_high(t["rvol"], 0.8, 2.0) * 0.20
    dividend_safety = score_high(dividend_yield, 1, 6) * 0.35 + score_range(payout_ratio, 20, 75, 1.2) * 0.30 + score_high(fcf_yield, 0, 8) * 0.20 + score_high(interest_coverage, 2, 12) * 0.15
    failure_penalty = (12 if t["price"] < t["vwap"] else 0) + (18 if t["upper_shadow"] > 3 and t["rvol"] > 1.5 else 0) + (10 if t["gap_pct"] > 6 else 0)
    risk_score = clamp(low_vol_score * 0.35 + liquidity_score * 0.25 + score_low(debt_to_equity, 50, 220) * 0.15 + score_high(current_ratio, 0.8, 2.5) * 0.10 + score_high(interest_coverage, 2, 12) * 0.10 + (100 - failure_penalty) * 0.05)
    factor_scores = {
        "value": clamp(value_score),
        "growth": clamp(growth_score),
        "quality": clamp(quality_score),
        "momentum": clamp(momentum_score),
        "low_vol": clamp(low_vol_score),
        "liquidity": clamp(liquidity_score),
        "risk": clamp(risk_score),
        "dividend_safety": clamp(dividend_safety),
    }
    weights = WEIGHTS[mode][style]
    win_score = round(sum(factor_scores[k] * w for k, w in weights.items()), 1)
    hard_flags = []
    preset = STYLE_MODE_PRESETS[(style, mode)]
    if t["volume"] < preset["min_volume"]:
        hard_flags.append("流動性不足")
    if t["atr_pct"] > preset["max_atr"]:
        hard_flags.append("波動過高")
    if style != "當沖" and t["price"] < t["ma200"] and mode == "黑馬模式":
        hard_flags.append("未站上長期趨勢")
    if mode == "白馬模式" and factor_scores["quality"] < 45:
        hard_flags.append("品質分數不足")
    if mode == "黑馬模式" and factor_scores["momentum"] < 55:
        hard_flags.append("動能分數不足")
    return {
        "symbol": symbol,
        "style": style,
        "mode": mode,
        "metrics": {**t, "pe": pe, "pb": pb, "ps": ps, "ev_ebitda": ev_ebitda, "roe": roe, "roa": roa, "roic": roic, "gross_margin": gross_margin, "op_margin": op_margin, "net_margin": net_margin, "debt_to_equity": debt_to_equity, "current_ratio": current_ratio, "interest_coverage": interest_coverage, "fcf_yield": fcf_yield, "dividend_yield": dividend_yield, "payout_ratio": payout_ratio, "revenue_growth": revenue_growth, "earnings_growth": earnings_growth, "eps_revision": eps_revision},
        "factor_scores": factor_scores,
        "weights": weights,
        "win_score": win_score,
        "white_score": round(sum(factor_scores[k] * WEIGHTS["白馬模式"][style][k] for k in weights), 1),
        "black_score": round(sum(factor_scores[k] * WEIGHTS["黑馬模式"][style][k] for k in weights), 1),
        "bucket": score_bucket(win_score),
        "hard_flags": hard_flags,
    }


def calculate_daytrade_matrix(intraday_df: pd.DataFrame | None) -> dict[str, Any]:
    if intraday_df is None:
        return {"available": False, "reason": "查無 5 分鐘線資料"}
    df = normalize_ohlcv(intraday_df)
    if len(df) < 30:
        return {"available": False, "reason": "5 分鐘線資料不足"}
    session = df[df.index.date == df.index.max().date()].copy() if isinstance(df.index, pd.DatetimeIndex) else df.tail(60).copy()
    if len(session) < 12:
        return {"available": False, "reason": "當日盤中資料不足"}
    close, high, low, volume = session["Close"], session["High"], session["Low"], session["Volume"]
    price = safe_float(close.iloc[-1])
    typical = (high + low + close) / 3
    intraday_vwap = safe_float((typical * volume).cumsum().iloc[-1] / volume.cumsum().iloc[-1]) if volume.cumsum().iloc[-1] > 0 else 0
    ema9 = safe_float(ema(close, 9).iloc[-1])
    ema21 = safe_float(ema(close, 21).iloc[-1])
    rsi_5m = safe_float(rsi(close).iloc[-1], 50)
    macd = safe_float(macd_diff(close).iloc[-1])
    atr_5m = safe_float((atr_pct(high, low, close) / 100 * close).iloc[-1])
    avg_bar_volume = safe_float(df["Volume"].rolling(20).mean().dropna().tail(20).mean())
    intraday_rvol = safe_float(volume.iloc[-1]) / avg_bar_volume if avg_bar_volume > 0 else 0
    open_range = session.head(6)
    orb_high = safe_float(open_range["High"].max())
    orb_low = safe_float(open_range["Low"].min())
    long_score = sum([25 if price > intraday_vwap > 0 else 0, 20 if ema9 > ema21 > 0 else 0, 25 if price > orb_high > 0 else 0, 15 if macd > 0 else 0, 15 if 45 <= rsi_5m <= 72 else 0])
    short_score = sum([25 if 0 < price < intraday_vwap else 0, 20 if 0 < ema9 < ema21 else 0, 25 if 0 < price < orb_low else 0, 15 if macd < 0 else 0, 15 if 28 <= rsi_5m <= 55 else 0])
    return {"available": True, "price": price, "day_high": safe_float(high.max()), "day_low": safe_float(low.min()), "day_volume": safe_float(volume.sum()), "intraday_vwap": intraday_vwap, "vwap_gap_pct": pct_change(price, intraday_vwap), "ema9": ema9, "ema21": ema21, "rsi_5m": rsi_5m, "macd_diff_5m": macd, "atr_5m_pct": atr_5m / price * 100 if price else 0, "intraday_rvol": intraday_rvol, "orb_high": orb_high, "orb_low": orb_low, "long_bias_score": long_score, "short_bias_score": short_score}


def get_light(engine: dict[str, Any], daytrade: dict[str, Any] | None = None, daytrade_direction: str = "做多") -> tuple[str, str]:
    if engine["hard_flags"]:
        return "紅燈", " / ".join(engine["hard_flags"]) + "，暫不啟動新倉位"
    if engine["style"] == "當沖" and daytrade and daytrade.get("available"):
        day_score = daytrade["long_bias_score"] if daytrade_direction == "做多" else daytrade["short_bias_score"]
        if day_score < 70:
            return "黃燈", "當沖盤中方向分數不足，等待下一根 5 分鐘 K 確認"
    score = engine["win_score"]
    if score >= 78:
        return "綠燈", "多因子共振，可進入紀律化執行清單"
    if score >= 62:
        return "藍燈", "條件接近成熟，等待價格或量能確認"
    if score >= 50:
        return "黃燈", "勝率條件不足，保留追蹤"
    return "紅燈", "多因子分數偏低，不建議啟動新倉位"


def build_trade_plan(engine: dict[str, Any], daytrade: dict[str, Any] | None = None, daytrade_direction: str = "做多") -> dict[str, Any]:
    price = safe_float(engine["metrics"]["price"])
    preset = STYLE_MODE_PRESETS[(engine["style"], engine["mode"])]
    if engine["style"] == "當沖" and daytrade and daytrade.get("available"):
        entry = safe_float(daytrade["price"])
        if daytrade_direction == "做多":
            stop = min(daytrade["intraday_vwap"], daytrade["orb_low"], entry * (1 - preset["stop"] / 100))
            risk = max(entry - stop, 0.01)
            return {"entry": entry, "stop": stop, "target_1": entry + risk * 1.5, "target_2": entry + risk * 2.5, "position_hint": "單筆風險 0.25%-0.5%，禁止攤平，收盤前清倉", "rr": 1.5}
        stop = max(daytrade["intraday_vwap"], daytrade["orb_high"], entry * (1 + preset["stop"] / 100))
        risk = max(stop - entry, 0.01)
        return {"entry": entry, "stop": stop, "target_1": entry - risk * 1.5, "target_2": entry - risk * 2.5, "position_hint": "單筆風險 0.25%-0.5%，禁止攤平，收盤前清倉", "rr": 1.5}
    stop = price * (1 - preset["stop"] / 100)
    risk = max(price - stop, 0.01)
    return {"entry": price, "stop": stop, "target_1": price * (1 + preset["target"] / 100), "target_2": price + risk * 3, "position_hint": f"{engine['style']} / {engine['mode']}：分批執行，單筆風險控制於 0.5%-1.0%", "rr": (price * (1 + preset["target"] / 100) - price) / risk}


def run_signal_backtest(hist: pd.DataFrame, params: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = normalize_ohlcv(hist)
    if len(df) < 120:
        return pd.DataFrame(), {"狀態": "資料不足，至少需要 120 個交易日"}
    params = {"hold": 20, "rvol": 1.2, "max_atr": 5.0, "stop": 8.0, "target": 16.0, "trailing": 10.0, "fee": 0.1425, "slippage": 0.1, **(params or {})}
    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    ma20, ma50 = close.rolling(20).mean(), close.rolling(50).mean()
    signal = (close > ma20) & (close > ma50) & rsi(close).between(45, 72) & (macd_diff(close) > 0) & ((volume / volume.rolling(20).mean()) >= params["rvol"]) & (atr_pct(high, low, close) <= params["max_atr"])
    trades, last_exit = [], -1
    for idx in range(60, len(df) - int(params["hold"]) - 1):
        if idx <= last_exit or not bool(signal.iloc[idx]):
            continue
        entry_idx = idx + 1
        entry = safe_float(df["Open"].iloc[entry_idx]) * (1 + params["slippage"] / 100)
        stop = entry * (1 - params["stop"] / 100)
        target = entry * (1 + params["target"] / 100)
        trailing, highest = stop, entry
        exit_idx = min(entry_idx + int(params["hold"]), len(df) - 1)
        exit_raw, reason, max_gain, max_drawdown = safe_float(close.iloc[exit_idx]), "持有期滿", 0.0, 0.0
        for scan_idx in range(entry_idx, min(entry_idx + int(params["hold"]), len(df) - 1) + 1):
            bar_high, bar_low = safe_float(high.iloc[scan_idx]), safe_float(low.iloc[scan_idx])
            highest = max(highest, bar_high)
            trailing = max(trailing, highest * (1 - params["trailing"] / 100))
            max_gain = max(max_gain, (bar_high - entry) / entry * 100)
            max_drawdown = min(max_drawdown, (bar_low - entry) / entry * 100)
            if bar_low <= trailing:
                exit_idx, exit_raw, reason = scan_idx, trailing, "移動/固定停損"
                break
            if bar_high >= target:
                exit_idx, exit_raw, reason = scan_idx, target, "停利"
                break
            exit_raw = safe_float(close.iloc[scan_idx])
        exit_price = exit_raw * (1 - params["slippage"] / 100)
        gross = (exit_price - entry) / entry * 100
        net = gross - params["fee"] * 2
        trades.append({"signal_date": df.index[idx], "entry_date": df.index[entry_idx], "exit_date": df.index[exit_idx], "entry": round(entry, 2), "exit": round(exit_price, 2), "exit_reason": reason, "holding_days": exit_idx - entry_idx + 1, "gross_return_pct": round(gross, 2), "net_return_pct": round(net, 2), "max_gain_pct": round(max_gain, 2), "max_drawdown_pct": round(max_drawdown, 2)})
        last_exit = exit_idx
    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return trades_df, {"狀態": "回測期間沒有符合條件的訊號"}
    returns = trades_df["net_return_pct"]
    wins, losses = returns[returns > 0], returns[returns <= 0]
    total_loss = abs(losses.sum()) if not losses.empty else 0
    return trades_df, {"交易次數": len(trades_df), "勝率%": round(len(wins) / len(trades_df) * 100, 1), "平均淨報酬%": round(returns.mean(), 2), "中位數淨報酬%": round(returns.median(), 2), "最佳單筆%": round(returns.max(), 2), "最差單筆%": round(returns.min(), 2), "平均最大回撤%": round(trades_df["max_drawdown_pct"].mean(), 2), "獲利因子": round(wins.sum() / total_loss, 2) if total_loss > 0 else 0, "平均持有日": round(trades_df["holding_days"].mean(), 1)}


def calculate_position_size(entry: float, stop: float, account_size: float, risk_pct: float, max_position_pct: float | None = None) -> dict[str, Any]:
    entry, stop, account_size, risk_pct = map(safe_float, [entry, stop, account_size, risk_pct])
    risk_per_share = abs(entry - stop)
    if entry <= 0 or stop <= 0 or account_size <= 0 or risk_pct <= 0 or risk_per_share <= 0:
        raise ValueError("entry, stop, account_size, risk_pct must be positive and entry must differ from stop")
    risk_amount = account_size * risk_pct / 100
    quantity = int(risk_amount // risk_per_share)
    max_notional = account_size * safe_float(max_position_pct, 100) / 100 if max_position_pct else None
    if max_notional:
        quantity = min(quantity, int(max_notional // entry))
    notional = quantity * entry
    return {"entry": entry, "stop": stop, "risk_per_share": round(risk_per_share, 4), "account_size": account_size, "risk_pct": risk_pct, "risk_amount": round(risk_amount, 2), "quantity": quantity, "notional": round(notional, 2), "actual_risk": round(quantity * risk_per_share, 2), "max_position_pct": max_position_pct}
