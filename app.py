from io import BytesIO

import pandas as pd
import streamlit as st
import yfinance as yf
import ta
from google import genai

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
except Exception:
    A4 = None
    getSampleStyleSheet = None
    pdfmetrics = None
    UnicodeCIDFont = None
    SimpleDocTemplate = None
    Paragraph = None
    Spacer = None


APP_TITLE = "WallWin Gem 華爾街致勝寶石"
APP_MISSION = "以提升投資勝率為使命，透過縝密、嚴謹、系統性的分析方法，提高股市交易獲利率。"
DISCLAIMER = "本系統輸出為投資決策輔助，不構成投資建議、保證獲利或保證勝率。"
MIN_ANALYSIS_DAYS = 200
DAYTRADE_INTERVAL = "5m"
DAYTRADE_PERIOD = "5d"


STYLE_MODE_PRESETS = {
    ("波段", "白馬模式"): {"min_volume": 200000, "max_atr": 5.0, "rvol": 1.4, "vcp": 12.0, "stop": 8.0, "target": 16.0, "hold": 20},
    ("波段", "黑馬模式"): {"min_volume": 300000, "max_atr": 7.0, "rvol": 2.0, "vcp": 8.0, "stop": 7.0, "target": 18.0, "hold": 15},
    ("投資", "白馬模式"): {"min_volume": 100000, "max_atr": 4.5, "rvol": 1.1, "vcp": 18.0, "stop": 15.0, "target": 30.0, "hold": 60},
    ("投資", "黑馬模式"): {"min_volume": 250000, "max_atr": 6.5, "rvol": 1.6, "vcp": 12.0, "stop": 12.0, "target": 28.0, "hold": 45},
    ("當沖", "白馬模式"): {"min_volume": 500000, "max_atr": 3.5, "rvol": 1.5, "vcp": 15.0, "stop": 1.2, "target": 2.0, "hold": 1},
    ("當沖", "黑馬模式"): {"min_volume": 800000, "max_atr": 5.0, "rvol": 2.2, "vcp": 10.0, "stop": 1.0, "target": 2.5, "hold": 1},
}

WEIGHTS = {
    "白馬模式": {
        "投資": {"value": 0.20, "growth": 0.15, "quality": 0.25, "momentum": 0.10, "low_vol": 0.10, "liquidity": 0.05, "risk": 0.15},
        "波段": {"value": 0.15, "growth": 0.15, "quality": 0.20, "momentum": 0.20, "low_vol": 0.10, "liquidity": 0.05, "risk": 0.15},
        "當沖": {"value": 0.05, "growth": 0.05, "quality": 0.10, "momentum": 0.35, "low_vol": 0.10, "liquidity": 0.20, "risk": 0.15},
    },
    "黑馬模式": {
        "投資": {"value": 0.10, "growth": 0.20, "quality": 0.15, "momentum": 0.25, "low_vol": 0.05, "liquidity": 0.10, "risk": 0.15},
        "波段": {"value": 0.05, "growth": 0.15, "quality": 0.10, "momentum": 0.35, "low_vol": 0.05, "liquidity": 0.15, "risk": 0.15},
        "當沖": {"value": 0.00, "growth": 0.05, "quality": 0.05, "momentum": 0.40, "low_vol": 0.05, "liquidity": 0.30, "risk": 0.15},
    },
}


def safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val) or str(val).strip() == "":
            return default
        return float(val)
    except Exception:
        return default


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def score_bucket(score):
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def pct_change(current, previous):
    if previous and previous > 0:
        return (current - previous) / previous * 100
    return 0.0


def get_secret_value(name, default=""):
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


def truthy_secret(name, default=False):
    value = get_secret_value(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "y", "on"}


def require_app_password():
    app_password = get_secret_value("APP_PASSWORD")
    if not app_password:
        st.warning("⚠️ 尚未設定 APP_PASSWORD；公開部署時建議在 Streamlit Secrets 加上密碼防護。")
        return
    if st.session_state.get("authenticated"):
        return
    st.subheader("🔐 WallWin Gem 存取驗證")
    password = st.text_input("請輸入 App 密碼", type="password")
    if st.button("登入", type="primary"):
        if password == app_password:
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("密碼錯誤，請重新輸入。")
    st.stop()


def resolve_ai_api_key():
    allow_owner_key = truthy_secret("ALLOW_OWNER_KEY", default=False)
    owner_key = get_secret_value("GEMINI_API_KEY") if allow_owner_key else ""
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔑 AI 報告 API Key")
    if allow_owner_key and owner_key:
        st.sidebar.success("Owner Key 模式已啟用")
        return owner_key, "owner"
    user_key = st.sidebar.text_input("Gemini API Key（由使用者自備）", type="password").strip()
    st.sidebar.caption("外部使用者若要產生 AI 報告，必須使用自己的 Gemini API Key。")
    return user_key, "user" if user_key else "missing"


def parse_watchlist(raw_text):
    tokens = raw_text.replace("\n", ",").replace("，", ",").split(",")
    return [token.strip().upper() for token in tokens if token.strip()]


def normalize_symbol_for_advanced(symbol):
    return symbol.upper().replace(".TW", "").replace(".TWO", "")


def get_advanced_row(advanced_df, symbol):
    if advanced_df is None or advanced_df.empty or "股號" not in advanced_df.columns:
        return {}
    try:
        normalized = normalize_symbol_for_advanced(symbol)
        rows = advanced_df[advanced_df["股號"].astype(str).str.upper().str.replace(".TW", "", regex=False).str.replace(".TWO", "", regex=False) == normalized]
        if rows.empty:
            return {}
        return {str(k): v for k, v in rows.iloc[0].to_dict().items() if pd.notna(v)}
    except Exception:
        return {}


def metric_value(info, advanced, key, alt_keys=None, default=0.0, pct=False):
    candidates = [key] + (alt_keys or [])
    for candidate in candidates:
        if candidate in advanced:
            value = safe_float(advanced[candidate], None)
            if value is not None:
                return value
        if candidate in info:
            value = safe_float(info.get(candidate), None)
            if value is not None:
                return value * 100 if pct and abs(value) <= 2 else value
    return default


def score_high(value, weak, strong):
    if value <= weak:
        return 0.0
    if value >= strong:
        return 100.0
    return (value - weak) / (strong - weak) * 100


def score_low(value, strong, weak):
    if value <= strong:
        return 100.0
    if value >= weak:
        return 0.0
    return (weak - value) / (weak - strong) * 100


def score_range(value, low, high, edge_penalty=0.6):
    if low <= value <= high:
        return 100.0
    distance = low - value if value < low else value - high
    return clamp(100 - distance * edge_penalty)


def fetch_benchmark(symbol):
    return "^TWII" if symbol.upper().endswith((".TW", ".TWO")) else "SPY"


@st.cache_data(ttl=1800)
def load_history(symbol, period="1y", interval="1d"):
    return yf.Ticker(symbol).history(period=period, interval=interval)


@st.cache_data(ttl=1800)
def load_info(symbol):
    try:
        return yf.Ticker(symbol).info or {}
    except Exception:
        return {}


def build_technical_pack(hist, benchmark_hist=None):
    df = hist.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    price = safe_float(close.iloc[-1])
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    atr = ta.volatility.AverageTrueRange(high=high, low=low, close=close).average_true_range()
    atr_pct = safe_float(atr.iloc[-1]) / price * 100 if price > 0 else 0
    rsi = safe_float(ta.momentum.RSIIndicator(close=close).rsi().iloc[-1], 50)
    macd_diff = safe_float(ta.trend.MACD(close=close).macd_diff().iloc[-1])
    adx = safe_float(ta.trend.ADXIndicator(high=high, low=low, close=close).adx().iloc[-1])
    bb = ta.volatility.BollingerBands(close=close)
    bb_width_series = (bb.bollinger_hband() - bb.bollinger_lband()) / close * 100
    bb_width = safe_float(bb_width_series.iloc[-1])
    bb_width_rank = (bb_width_series.dropna().rank(pct=True).iloc[-1] * 100) if len(bb_width_series.dropna()) else 50
    vol20 = volume.rolling(20).mean()
    rvol = safe_float(volume.iloc[-1]) / safe_float(vol20.iloc[-1], 1)
    vwap = safe_float(ta.volume.VolumeWeightedAveragePrice(high=high, low=low, close=close, volume=volume).volume_weighted_average_price().iloc[-1])
    low_min_20 = low.tail(20).min()
    vcp = ((high.tail(20).max() - low_min_20) / low_min_20 * 100) if low_min_20 > 0 else 0
    dollar_volume = price * safe_float(volume.iloc[-1])
    high_52w = safe_float(high.tail(252).max())
    dist_52w_high = pct_change(price, high_52w)
    ma50_slope = pct_change(safe_float(ma50.iloc[-1]), safe_float(ma50.iloc[-21])) if len(ma50.dropna()) > 21 else 0
    ma200_slope = pct_change(safe_float(ma200.iloc[-1]), safe_float(ma200.iloc[-21])) if len(ma200.dropna()) > 21 else 0
    closes_above_breakout = close.tail(5).gt(high.tail(25).iloc[:-5].max() if len(high) >= 25 else high.tail(20).max()).sum()
    upper_shadow = (high.iloc[-1] - max(close.iloc[-1], df["Open"].iloc[-1])) / price * 100 if price > 0 else 0
    gap_pct = pct_change(df["Open"].iloc[-1], close.iloc[-2]) if len(df) > 2 else 0
    returns = {}
    for label, days in {"1m": 21, "3m": 63, "6m": 126}.items():
        returns[label] = pct_change(price, safe_float(close.iloc[-days])) if len(close) > days else 0
    benchmark_returns = {"1m": 0, "3m": 0, "6m": 0}
    if benchmark_hist is not None and not benchmark_hist.empty:
        b_close = benchmark_hist["Close"].dropna()
        b_price = safe_float(b_close.iloc[-1])
        for label, days in {"1m": 21, "3m": 63, "6m": 126}.items():
            benchmark_returns[label] = pct_change(b_price, safe_float(b_close.iloc[-days])) if len(b_close) > days else 0
    rel_strength = sum(returns[k] - benchmark_returns[k] for k in returns) / 3
    return {
        "price": price,
        "volume": safe_float(volume.iloc[-1]),
        "dollar_volume": dollar_volume,
        "ma20": safe_float(ma20.iloc[-1]),
        "ma50": safe_float(ma50.iloc[-1]),
        "ma200": safe_float(ma200.iloc[-1]),
        "ma50_slope": ma50_slope,
        "ma200_slope": ma200_slope,
        "rvol": rvol,
        "vcp": vcp,
        "vwap": vwap,
        "atr_pct": atr_pct,
        "rsi": rsi,
        "macd_diff": macd_diff,
        "adx": adx,
        "bb_width": bb_width,
        "bb_width_rank": safe_float(bb_width_rank),
        "dist_52w_high": dist_52w_high,
        "rel_strength": rel_strength,
        "return_1m": returns["1m"],
        "return_3m": returns["3m"],
        "return_6m": returns["6m"],
        "close_above_breakout_days": int(closes_above_breakout),
        "upper_shadow": upper_shadow,
        "gap_pct": gap_pct,
        "data_points": len(df),
    }


def score_multifactor(symbol, info, hist, advanced, style, mode):
    benchmark_hist = load_history(fetch_benchmark(symbol), period="1y")
    t = build_technical_pack(hist, benchmark_hist)
    price = t["price"]
    revenue_growth = metric_value(info, advanced, "revenueGrowth", ["營收YoY", "revenue_yoy"], pct=True)
    earnings_growth = metric_value(info, advanced, "earningsGrowth", ["EPSYoY", "eps_yoy"], pct=True)
    gross_margin = metric_value(info, advanced, "grossMargins", ["毛利率", "gross_margin"], pct=True)
    op_margin = metric_value(info, advanced, "operatingMargins", ["營益率", "operating_margin"], pct=True)
    net_margin = metric_value(info, advanced, "profitMargins", ["淨利率", "net_margin"], pct=True)
    roe = metric_value(info, advanced, "returnOnEquity", ["ROE"], pct=True)
    roa = metric_value(info, advanced, "returnOnAssets", ["ROA"], pct=True)
    roic = metric_value(info, advanced, "ROIC", ["roic"], pct=True)
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

    value_score = (
        score_low(pe, 10, 35) * 0.22
        + score_low(pb, 1.0, 5.0) * 0.18
        + score_low(ps, 1.0, 8.0) * 0.12
        + score_low(ev_ebitda, 6, 25) * 0.12
        + score_high(fcf_yield, 0, 8) * 0.16
        + score_low(pe_percentile, 20, 80) * 0.10
        + score_low(pb_percentile, 20, 80) * 0.10
    )
    growth_score = (
        score_high(revenue_growth, -5, 30) * 0.30
        + score_high(earnings_growth, -10, 35) * 0.35
        + score_high(eps_revision, -10, 20) * 0.20
        + score_high(t["return_6m"], -15, 35) * 0.15
    )
    quality_score = (
        score_high(roe, 5, 25) * 0.20
        + score_high(roa, 2, 12) * 0.12
        + score_high(roic, 5, 20) * 0.13
        + score_high(gross_margin, 15, 55) * 0.15
        + score_high(op_margin, 5, 25) * 0.15
        + score_high(net_margin, 3, 20) * 0.10
        + score_high(ocf, 0, max(abs(fcf), 1)) * 0.05
        + score_low(debt_to_equity, 40, 180) * 0.10
    )
    momentum_score = (
        score_high(t["rel_strength"], -10, 25) * 0.18
        + score_high(t["ma50_slope"], -5, 12) * 0.12
        + score_high(t["ma200_slope"], -5, 10) * 0.10
        + score_range(t["rsi"], 45, 72, 2.0) * 0.12
        + (100 if t["macd_diff"] > 0 else 30) * 0.10
        + score_high(t["adx"], 12, 35) * 0.10
        + score_high(t["rvol"], 0.8, 2.5) * 0.12
        + score_low(abs(t["dist_52w_high"]), 0, 35) * 0.08
        + score_low(t["vcp"], 4, 18) * 0.08
        + score_high(t["close_above_breakout_days"], 0, 4) * 0.10
    )
    low_vol_score = (
        score_low(t["atr_pct"], 2.5, 9.0) * 0.40
        + score_low(t["bb_width_rank"], 20, 90) * 0.30
        + score_low(abs(t["gap_pct"]), 0.5, 6.0) * 0.30
    )
    liquidity_score = (
        score_high(t["volume"] / 1000, 100, 5000) * 0.35
        + score_high(t["dollar_volume"], 50_000_000, 2_000_000_000) * 0.45
        + score_high(t["rvol"], 0.8, 2.0) * 0.20
    )
    dividend_safety = (
        score_high(dividend_yield, 1, 6) * 0.35
        + score_range(payout_ratio, 20, 75, 1.2) * 0.30
        + score_high(fcf_yield, 0, 8) * 0.20
        + score_high(interest_coverage, 2, 12) * 0.15
    )
    failure_penalty = 0
    if price < t["vwap"]:
        failure_penalty += 12
    if t["upper_shadow"] > 3 and t["rvol"] > 1.5:
        failure_penalty += 18
    if t["gap_pct"] > 6:
        failure_penalty += 10
    risk_score = clamp(
        low_vol_score * 0.35
        + liquidity_score * 0.25
        + score_low(debt_to_equity, 50, 220) * 0.15
        + score_high(current_ratio, 0.8, 2.5) * 0.10
        + score_high(interest_coverage, 2, 12) * 0.10
        + (100 - failure_penalty) * 0.05
    )

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
    white_score = round(sum(factor_scores[k] * WEIGHTS["白馬模式"][style][k] for k in weights), 1)
    black_score = round(sum(factor_scores[k] * WEIGHTS["黑馬模式"][style][k] for k in weights), 1)
    hard_flags = []
    preset = STYLE_MODE_PRESETS[(style, mode)]
    if t["volume"] < preset["min_volume"]:
        hard_flags.append("流動性不足")
    if t["atr_pct"] > preset["max_atr"]:
        hard_flags.append("波動過高")
    if style != "當沖" and price < t["ma200"] and mode == "黑馬模式":
        hard_flags.append("未站上長期趨勢")
    if mode == "白馬模式" and factor_scores["quality"] < 45:
        hard_flags.append("品質分數不足")
    if mode == "黑馬模式" and factor_scores["momentum"] < 55:
        hard_flags.append("動能分數不足")

    metrics = {
        **t,
        "pe": pe,
        "pb": pb,
        "ps": ps,
        "ev_ebitda": ev_ebitda,
        "roe": roe,
        "roa": roa,
        "roic": roic,
        "gross_margin": gross_margin,
        "op_margin": op_margin,
        "net_margin": net_margin,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
        "interest_coverage": interest_coverage,
        "fcf_yield": fcf_yield,
        "dividend_yield": dividend_yield,
        "payout_ratio": payout_ratio,
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "eps_revision": eps_revision,
    }
    return {
        "symbol": symbol,
        "style": style,
        "mode": mode,
        "metrics": metrics,
        "factor_scores": factor_scores,
        "win_score": win_score,
        "white_score": white_score,
        "black_score": black_score,
        "bucket": score_bucket(win_score),
        "hard_flags": hard_flags,
        "advanced": advanced,
    }


def calculate_daytrade_matrix(intraday_df):
    if intraday_df is None or intraday_df.empty:
        return {"available": False, "reason": "查無 5 分鐘線資料"}
    df = intraday_df.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(df) < 30:
        return {"available": False, "reason": "5 分鐘線資料不足"}
    session = df[df.index.date == df.index.max().date()].copy() if isinstance(df.index, pd.DatetimeIndex) else df.tail(60).copy()
    if len(session) < 12:
        return {"available": False, "reason": "當日盤中資料不足"}
    close = session["Close"]
    high = session["High"]
    low = session["Low"]
    volume = session["Volume"]
    price = safe_float(close.iloc[-1])
    typical = (high + low + close) / 3
    intraday_vwap = safe_float((typical * volume).cumsum().iloc[-1] / volume.cumsum().iloc[-1]) if volume.cumsum().iloc[-1] > 0 else 0
    ema9 = safe_float(close.ewm(span=9, adjust=False).mean().iloc[-1])
    ema21 = safe_float(close.ewm(span=21, adjust=False).mean().iloc[-1])
    rsi_5m = safe_float(ta.momentum.RSIIndicator(close=close, window=14).rsi().iloc[-1], 50)
    macd_diff = safe_float(ta.trend.MACD(close=close).macd_diff().iloc[-1])
    atr_5m = safe_float(ta.volatility.AverageTrueRange(high=high, low=low, close=close).average_true_range().iloc[-1])
    avg_bar_volume = safe_float(df["Volume"].rolling(20).mean().dropna().tail(20).mean())
    intraday_rvol = safe_float(volume.iloc[-1]) / avg_bar_volume if avg_bar_volume > 0 else 0
    open_range = session.head(6)
    orb_high = safe_float(open_range["High"].max())
    orb_low = safe_float(open_range["Low"].min())
    long_score = sum([
        25 if price > intraday_vwap > 0 else 0,
        20 if ema9 > ema21 > 0 else 0,
        25 if price > orb_high > 0 else 0,
        15 if macd_diff > 0 else 0,
        15 if 45 <= rsi_5m <= 72 else 0,
    ])
    short_score = sum([
        25 if 0 < price < intraday_vwap else 0,
        20 if 0 < ema9 < ema21 else 0,
        25 if 0 < price < orb_low else 0,
        15 if macd_diff < 0 else 0,
        15 if 28 <= rsi_5m <= 55 else 0,
    ])
    return {
        "available": True,
        "price": price,
        "day_high": safe_float(high.max()),
        "day_low": safe_float(low.min()),
        "day_volume": safe_float(volume.sum()),
        "intraday_vwap": intraday_vwap,
        "vwap_gap_pct": pct_change(price, intraday_vwap),
        "ema9": ema9,
        "ema21": ema21,
        "rsi_5m": rsi_5m,
        "macd_diff_5m": macd_diff,
        "atr_5m_pct": atr_5m / price * 100 if price > 0 else 0,
        "intraday_rvol": intraday_rvol,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "long_bias_score": long_score,
        "short_bias_score": short_score,
    }


def get_light(engine, daytrade=None, daytrade_direction="做多"):
    if engine["hard_flags"]:
        return "🔴 紅燈", " / ".join(engine["hard_flags"]) + "，暫不啟動新倉位"
    score = engine["win_score"]
    if engine["style"] == "當沖" and daytrade and daytrade.get("available"):
        day_score = daytrade["long_bias_score"] if daytrade_direction == "做多" else daytrade["short_bias_score"]
        if day_score < 70:
            return "🟡 黃燈", "當沖盤中方向分數不足，等待下一根 5 分鐘 K 確認"
    if score >= 78:
        return "🟢 綠燈", "多因子共振，可進入紀律化執行清單"
    if score >= 62:
        return "🔵 藍燈", "條件接近成熟，等待價格或量能確認"
    if score >= 50:
        return "🟡 黃燈", "勝率條件不足，保留追蹤"
    return "🔴 紅燈", "多因子分數偏低，不建議啟動新倉位"


def build_trade_plan(engine, daytrade=None, daytrade_direction="做多"):
    m = engine["metrics"]
    price = m["price"]
    preset = STYLE_MODE_PRESETS[(engine["style"], engine["mode"])]
    if engine["style"] == "當沖" and daytrade and daytrade.get("available"):
        entry = daytrade["price"]
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


def run_signal_backtest(hist, params):
    df = hist.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(df) < 120:
        return pd.DataFrame(), {"狀態": "資料不足，至少需要 120 個交易日"}
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    rsi = ta.momentum.RSIIndicator(close=close).rsi()
    macd = ta.trend.MACD(close=close).macd_diff()
    atr_pct = ta.volatility.AverageTrueRange(high=high, low=low, close=close).average_true_range() / close * 100
    rvol = volume / volume.rolling(20).mean()
    signal = (close > ma20) & (close > ma50) & rsi.between(45, 72) & (macd > 0) & (rvol >= params["rvol"]) & (atr_pct <= params["max_atr"])
    trades = []
    last_exit = -1
    for idx in range(60, len(df) - params["hold"] - 1):
        if idx <= last_exit or not bool(signal.iloc[idx]):
            continue
        entry_idx = idx + 1
        entry = safe_float(df["Open"].iloc[entry_idx]) * (1 + params["slippage"] / 100)
        stop = entry * (1 - params["stop"] / 100)
        target = entry * (1 + params["target"] / 100)
        trailing = stop
        highest = entry
        exit_idx = min(entry_idx + params["hold"], len(df) - 1)
        exit_raw = safe_float(close.iloc[exit_idx])
        reason = "持有期滿"
        max_gain = 0.0
        max_drawdown = 0.0
        for scan_idx in range(entry_idx, min(entry_idx + params["hold"], len(df) - 1) + 1):
            bar_high = safe_float(high.iloc[scan_idx])
            bar_low = safe_float(low.iloc[scan_idx])
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
        trades.append({"訊號日": df.index[idx].date(), "進場日": df.index[entry_idx].date(), "出場日": df.index[exit_idx].date(), "進場價": round(entry, 2), "出場價": round(exit_price, 2), "出場原因": reason, "持有日": exit_idx - entry_idx + 1, "毛報酬率%": round(gross, 2), "淨報酬率%": round(net, 2), "期間最大漲幅%": round(max_gain, 2), "期間最大回撤%": round(max_drawdown, 2)})
        last_exit = exit_idx
    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return trades_df, {"狀態": "回測期間沒有符合條件的訊號"}
    returns = trades_df["淨報酬率%"]
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    total_loss = abs(losses.sum()) if not losses.empty else 0
    return trades_df, {"交易次數": len(trades_df), "勝率%": round(len(wins) / len(trades_df) * 100, 1), "平均淨報酬%": round(returns.mean(), 2), "中位數淨報酬%": round(returns.median(), 2), "最佳單筆%": round(returns.max(), 2), "最差單筆%": round(returns.min(), 2), "平均最大回撤%": round(trades_df["期間最大回撤%"].mean(), 2), "獲利因子": round(wins.sum() / total_loss, 2) if total_loss > 0 else 0, "平均持有日": round(trades_df["持有日"].mean(), 1)}


def hitl_recommendations(style, mode):
    base = ["股號", "產業", "同業排名", "財報備註"]
    if mode == "白馬模式":
        base += ["ROE", "ROA", "ROIC", "毛利率", "營益率", "淨利率", "負債權益比", "流動比率", "利息保障倍數", "自由現金流", "FCF殖利率", "PE分位", "PB分位", "配息率"]
    else:
        base += ["營收YoY", "EPSYoY", "分析師上修", "法人買超", "主力籌碼", "產業強度", "突破型態備註", "事件催化"]
    if style == "當沖":
        base += ["盤中催化", "新聞時間", "券資變化", "隔日沖風險"]
    return base


def build_hitl_template(style, mode):
    columns = hitl_recommendations(style, mode)
    sample = {column: "" for column in columns}
    sample["股號"] = "2330.TW"
    if "ROE" in sample:
        sample.update({"ROE": 25, "ROA": 12, "ROIC": 18, "毛利率": 55, "營益率": 42, "淨利率": 38})
    if "營收YoY" in sample:
        sample.update({"營收YoY": 20, "EPSYoY": 25, "分析師上修": 10, "事件催化": "新產品/產業題材"})
    return pd.DataFrame([sample])


def hitl_coverage(advanced_df, style, mode):
    if advanced_df is None or advanced_df.empty:
        return 0, []
    recommended = hitl_recommendations(style, mode)
    present = [column for column in recommended if column in advanced_df.columns]
    return round(len(present) / max(len(recommended), 1) * 100, 1), [column for column in recommended if column not in present]


def profile_weights(base_weights, profile):
    adjusted = dict(base_weights)
    if profile == "品質價值強化":
        for key in ["value", "quality", "risk"]:
            adjusted[key] = adjusted.get(key, 0) + 0.05
        for key in ["momentum", "liquidity"]:
            adjusted[key] = max(adjusted.get(key, 0) - 0.05, 0)
    elif profile == "動能突破強化":
        for key in ["momentum", "liquidity", "growth"]:
            adjusted[key] = adjusted.get(key, 0) + 0.05
        for key in ["value", "low_vol", "quality"]:
            adjusted[key] = max(adjusted.get(key, 0) - 0.05, 0)
    elif profile == "風控防守強化":
        for key in ["risk", "low_vol", "quality"]:
            adjusted[key] = adjusted.get(key, 0) + 0.05
        for key in ["momentum", "growth", "liquidity"]:
            adjusted[key] = max(adjusted.get(key, 0) - 0.05, 0)
    total = sum(adjusted.values())
    return {key: value / total for key, value in adjusted.items()} if total else base_weights


def weighted_factor_score(factor_scores, weights):
    return round(sum(factor_scores.get(key, 0) * value for key, value in weights.items()), 1)


def calibrate_weight_profiles(engine):
    base = WEIGHTS[engine["mode"]][engine["style"]]
    profiles = ["原始權重", "品質價值強化", "動能突破強化", "風控防守強化"]
    rows = []
    for profile in profiles:
        weights = base if profile == "原始權重" else profile_weights(base, profile)
        score = weighted_factor_score(engine["factor_scores"], weights)
        rows.append(
            {
                "權重輪廓": profile,
                "重新加權分數": score,
                "分級": score_bucket(score),
                "Value權重": round(weights.get("value", 0), 2),
                "Growth權重": round(weights.get("growth", 0), 2),
                "Quality權重": round(weights.get("quality", 0), 2),
                "Momentum權重": round(weights.get("momentum", 0), 2),
                "Risk權重": round(weights.get("risk", 0), 2),
            }
        )
    return pd.DataFrame(rows).sort_values("重新加權分數", ascending=False)


def markdown_to_pdf_bytes(markdown_text):
    if SimpleDocTemplate is None:
        raise RuntimeError("PDF 套件未安裝，請確認 requirements.txt 包含 reportlab。")
    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    for style_name in ["Title", "Heading2", "BodyText"]:
        styles[style_name].fontName = "STSong-Light"
        styles[style_name].leading = max(styles[style_name].leading, 16)
    story = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 8))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], styles["Heading2"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + line[2:], styles["BodyText"]))
        elif not line.startswith("---"):
            story.append(Paragraph(line, styles["BodyText"]))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def build_report_markdown(symbol, engine, light, advice, trade_plan, full_report):
    m = engine["metrics"]
    return f"""# {APP_TITLE} 投審報告

## 結論
- 標的：{symbol}
- 交易週期：{engine['style']}
- 模式：{engine['mode']}
- 燈號：{light}
- 判定：{advice}
- 勝率分數：{engine['win_score']:.1f}/100 ({engine['bucket']})

## 多因子分數
- Value：{engine['factor_scores']['value']:.1f}
- Growth：{engine['factor_scores']['growth']:.1f}
- Quality：{engine['factor_scores']['quality']:.1f}
- Momentum：{engine['factor_scores']['momentum']:.1f}
- Low Volatility：{engine['factor_scores']['low_vol']:.1f}
- Liquidity：{engine['factor_scores']['liquidity']:.1f}
- Risk Control：{engine['factor_scores']['risk']:.1f}

## 交易框架
- 進場/觀察價：{trade_plan['entry']:.2f}
- 停損：{trade_plan['stop']:.2f}
- 目標一：{trade_plan['target_1']:.2f}
- 目標二：{trade_plan['target_2']:.2f}
- 部位：{trade_plan['position_hint']}

## AI 報告
{full_report}

---
{DISCLAIMER}
"""


st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title("💎 " + APP_TITLE)
st.caption(APP_MISSION)
st.caption(DISCLAIMER)
require_app_password()

st.sidebar.header("⚙️ 投審控制台")
ai_api_key, ai_key_source = resolve_ai_api_key()
symbol = st.sidebar.text_input("🎯 目標股號", "2206.TW").strip().upper()
style = st.sidebar.radio("交易週期", ["波段", "投資", "當沖"], horizontal=True)
mode = st.sidebar.radio("投審模式", ["白馬模式", "黑馬模式"], horizontal=True)
preset = STYLE_MODE_PRESETS[(style, mode)]

st.sidebar.markdown("---")
st.sidebar.subheader("🎚️ 自適配投審參數")
with st.sidebar.expander("依選擇自動套用，可人工微調", expanded=True):
    min_volume = st.slider("最低成交量門檻（股）", 50_000, 5_000_000, preset["min_volume"], 50_000)
    max_atr = st.slider("ATR 風險上限 (%)", 1.0, 12.0, float(preset["max_atr"]), 0.5)
    rvol_threshold = st.slider("RVOL 門檻", 1.0, 5.0, float(preset["rvol"]), 0.1)
    vcp_threshold = st.slider("VCP 壓縮限度 (%)", 3.0, 25.0, float(preset["vcp"]), 0.5)

st.sidebar.subheader("📁 HITL 私房數據")
recommended_cols = hitl_recommendations(style, mode)
st.sidebar.info("建議上傳欄位：" + "、".join(recommended_cols[:12]) + ("..." if len(recommended_cols) > 12 else ""))
st.sidebar.download_button(
    "下載 HITL CSV 模板",
    build_hitl_template(style, mode).to_csv(index=False).encode("utf-8-sig"),
    file_name=f"wallwin_hitl_template_{style}_{mode}.csv",
    mime="text/csv",
)
uploaded_file = st.sidebar.file_uploader("上傳 CSV，第一欄建議為「股號」", type="csv")
advanced_data = pd.read_csv(uploaded_file) if uploaded_file else None
coverage_pct, missing_hitl_cols = hitl_coverage(advanced_data, style, mode)
if uploaded_file:
    st.sidebar.success(f"HITL 欄位覆蓋率：{coverage_pct:.1f}%")
    if missing_hitl_cols:
        st.sidebar.caption("仍缺：" + "、".join(missing_hitl_cols[:8]) + ("..." if len(missing_hitl_cols) > 8 else ""))

st.sidebar.subheader("🛠️ HITL 人工校準")
with st.sidebar.expander("基本面/催化/風險覆寫", expanded=False):
    manual_peg = st.number_input("PEG 覆寫（0 表示不覆寫）", 0.0, 10.0, 0.0, 0.1)
    manual_catalyst = st.slider("事件催化加分", -20, 20, 0, 1)
    manual_risk = st.slider("人工風險扣分", 0, 30, 0, 1)
    manual_note = st.text_area("人工備註", height=80)

analyze_button = st.sidebar.button("🚀 啟動多因子投審", type="primary", use_container_width=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📡 Watchlist 多檔掃描")
watchlist_symbols = st.sidebar.text_area("股票清單", "2330.TW, 2317.TW, 2454.TW, 2206.TW", height=80)
scan_button = st.sidebar.button("📡 掃描 Watchlist", use_container_width=True)

if scan_button:
    symbols = parse_watchlist(watchlist_symbols)
    if len(symbols) > 20:
        st.error("單次最多掃描 20 檔。")
        st.stop()
    rows = []
    progress = st.progress(0, text="Watchlist 掃描中")
    for idx, item in enumerate(symbols, start=1):
        try:
            hist = load_history(item, period="1y")
            info = load_info(item)
            if hist.empty or len(hist) < 60:
                rows.append({"股號": item, "狀態": "資料不足"})
                continue
            engine = score_multifactor(item, info, hist, get_advanced_row(advanced_data, item), style, mode)
            rows.append({"股號": item, "勝率分數": engine["win_score"], "分級": engine["bucket"], "白馬分": engine["white_score"], "黑馬分": engine["black_score"], "Value": round(engine["factor_scores"]["value"], 1), "Growth": round(engine["factor_scores"]["growth"], 1), "Quality": round(engine["factor_scores"]["quality"], 1), "Momentum": round(engine["factor_scores"]["momentum"], 1), "Liquidity": round(engine["factor_scores"]["liquidity"], 1), "否決": "、".join(engine["hard_flags"]), "狀態": "OK"})
        except Exception as exc:
            rows.append({"股號": item, "狀態": f"錯誤：{exc}"})
        progress.progress(idx / len(symbols), text=f"Watchlist 掃描中：{idx}/{len(symbols)}")
    progress.empty()
    result_df = pd.DataFrame(rows)
    if "勝率分數" in result_df.columns:
        result_df = result_df.sort_values("勝率分數", ascending=False)
    st.subheader("📡 Watchlist 多因子掃描")
    st.dataframe(result_df, use_container_width=True, hide_index=True)
    st.download_button("下載 Watchlist CSV", result_df.to_csv(index=False).encode("utf-8-sig"), "wallwin_watchlist.csv", "text/csv")

if analyze_button:
    hist = load_history(symbol, period="1y")
    info = load_info(symbol)
    if hist.empty or len(hist) < 60:
        st.error("查無足夠資料或標的已下市。")
        st.stop()
    advanced = get_advanced_row(advanced_data, symbol)
    if manual_peg > 0:
        advanced["PEG"] = manual_peg
    engine = score_multifactor(symbol, info, hist, advanced, style, mode)
    engine["win_score"] = clamp(engine["win_score"] + manual_catalyst - manual_risk)
    engine["bucket"] = score_bucket(engine["win_score"])
    daytrade = calculate_daytrade_matrix(load_history(symbol, DAYTRADE_PERIOD, DAYTRADE_INTERVAL)) if style == "當沖" else None
    daytrade_direction = "做多"
    light, advice = get_light(engine, daytrade, daytrade_direction)
    trade_plan = build_trade_plan(engine, daytrade, daytrade_direction)
    m = engine["metrics"]

    st.subheader(f"{symbol} 投審結論")
    top_cols = st.columns(5)
    top_cols[0].metric("燈號", light)
    top_cols[1].metric("勝率分數", f"{engine['win_score']:.1f}", engine["bucket"])
    top_cols[2].metric("白馬分", f"{engine['white_score']:.1f}")
    top_cols[3].metric("黑馬分", f"{engine['black_score']:.1f}")
    top_cols[4].metric("最新價", f"{m['price']:.2f}")
    st.info(advice)
    if manual_note:
        st.caption("HITL 備註：" + manual_note)

    tab_matrix, tab_fundamental, tab_technical, tab_backtest, tab_calibration, tab_plan, tab_ai = st.tabs(["多因子矩陣", "白馬基本面", "黑馬技術面", "策略回測", "權重校準", "交易計畫", "AI 報告"])
    with tab_matrix:
        factor_df = pd.DataFrame([{"因子": k, "分數": round(v, 1), "權重": WEIGHTS[mode][style].get(k, 0)} for k, v in engine["factor_scores"].items()])
        st.dataframe(factor_df, use_container_width=True, hide_index=True)
        st.bar_chart(factor_df.set_index("因子")["分數"])
        if engine["hard_flags"]:
            st.error("否決條件：" + "、".join(engine["hard_flags"]))
    with tab_fundamental:
        st.write(f"ROE **{m['roe']:.2f}%** │ ROA **{m['roa']:.2f}%** │ ROIC **{m['roic']:.2f}%** │ 毛利率 **{m['gross_margin']:.2f}%** │ 營益率 **{m['op_margin']:.2f}%** │ 淨利率 **{m['net_margin']:.2f}%**")
        st.write(f"Debt/Equity **{m['debt_to_equity']:.2f}** │ Current Ratio **{m['current_ratio']:.2f}** │ Interest Coverage **{m['interest_coverage']:.2f}**")
        st.write(f"P/E **{m['pe']:.2f}** │ P/B **{m['pb']:.2f}** │ P/S **{m['ps']:.2f}** │ EV/EBITDA **{m['ev_ebitda']:.2f}** │ FCF Yield **{m['fcf_yield']:.2f}%**")
        st.write(f"殖利率 **{m['dividend_yield']:.2f}%** │ 配息率 **{m['payout_ratio']:.2f}%** │ Dividend Safety **{engine['factor_scores']['dividend_safety']:.1f}**")
    with tab_technical:
        st.line_chart(hist[["Close"]].tail(160))
        st.write(f"相對強弱 **{m['rel_strength']:.2f}%** │ MA50 slope **{m['ma50_slope']:.2f}%** │ MA200 slope **{m['ma200_slope']:.2f}%** │ 52週高點距離 **{m['dist_52w_high']:.2f}%**")
        st.write(f"RVOL **{m['rvol']:.2f}x** │ VCP **{m['vcp']:.2f}%** │ RSI **{m['rsi']:.1f}** │ ADX **{m['adx']:.1f}** │ ATR **{m['atr_pct']:.2f}%**")
        st.write(f"VWAP **{m['vwap']:.2f}** │ 布林寬度分位 **{m['bb_width_rank']:.1f}** │ Gap **{m['gap_pct']:.2f}%** │ 上影線 **{m['upper_shadow']:.2f}%**")
        if style == "當沖" and daytrade and daytrade.get("available"):
            st.write(f"當沖 VWAP **{daytrade['intraday_vwap']:.2f}** │ 5m RVOL **{daytrade['intraday_rvol']:.2f}x** │ 5m RSI **{daytrade['rsi_5m']:.1f}** │ 做多分 **{daytrade['long_bias_score']}** │ 放空分 **{daytrade['short_bias_score']}**")
    with tab_backtest:
        st.subheader("策略回測")
        bt_cols = st.columns(4)
        bt_params = {
            "hold": bt_cols[0].slider("最長持有天數", 5, 80, int(preset["hold"]), 5),
            "rvol": bt_cols[1].slider("RVOL 門檻", 1.0, 4.0, float(rvol_threshold), 0.1),
            "max_atr": bt_cols[2].slider("ATR 上限", 1.0, 12.0, float(max_atr), 0.5),
            "stop": bt_cols[3].slider("固定停損%", 1.0, 25.0, float(preset["stop"]), 0.5),
            "target": st.slider("停利%", 2.0, 50.0, float(preset["target"]), 1.0),
            "trailing": st.slider("移動停損%", 2.0, 30.0, 10.0, 0.5),
            "fee": st.slider("單邊交易成本%", 0.0, 1.0, 0.1425, 0.01),
            "slippage": st.slider("單邊滑價%", 0.0, 1.0, 0.10, 0.01),
        }
        trades_df, stats = run_signal_backtest(hist, bt_params)
        if trades_df.empty:
            st.warning(stats.get("狀態", "沒有可顯示的回測結果"))
        else:
            stat_cols = st.columns(4)
            stat_cols[0].metric("交易次數", stats["交易次數"])
            stat_cols[1].metric("勝率", f"{stats['勝率%']:.1f}%")
            stat_cols[2].metric("平均淨報酬", f"{stats['平均淨報酬%']:.2f}%")
            stat_cols[3].metric("獲利因子", f"{stats['獲利因子']:.2f}")
            st.caption("採下一交易日開盤進場，逐日檢查停損、停利、移動停損；同日停損/停利同時觸發時採保守停損。")
            st.dataframe(trades_df.tail(40), use_container_width=True, hide_index=True)
            st.download_button("下載回測 CSV", trades_df.to_csv(index=False).encode("utf-8-sig"), f"{symbol}_backtest.csv", "text/csv")
    with tab_calibration:
        st.subheader("權重校準與輪廓比較")
        calibration_df = calibrate_weight_profiles(engine)
        st.dataframe(calibration_df, use_container_width=True, hide_index=True)
        best_profile = calibration_df.iloc[0]
        st.info(
            f"目前資料下最佳輪廓：{best_profile['權重輪廓']}，"
            f"重新加權分數 {best_profile['重新加權分數']:.1f}（{best_profile['分級']}）。"
        )
        st.caption("此校準為目前標的的因子輪廓比較，下一步可再加入多年度 walk-forward 回測做嚴格參數校準。")
    with tab_plan:
        plan_cols = st.columns(4)
        plan_cols[0].metric("進場/觀察", f"{trade_plan['entry']:.2f}")
        plan_cols[1].metric("停損", f"{trade_plan['stop']:.2f}")
        plan_cols[2].metric("目標一", f"{trade_plan['target_1']:.2f}")
        plan_cols[3].metric("目標二", f"{trade_plan['target_2']:.2f}")
        st.write(trade_plan["position_hint"])
    with tab_ai:
        if not ai_api_key:
            st.warning("請在左側輸入使用者自備 Gemini API Key。")
            st.stop()
        ai_client = genai.Client(api_key=ai_api_key)
        prompt = f"""
        你是華爾街投審分析師。請以繁體中文輸出投審報告。
        標的：{symbol}
        交易週期：{style}
        模式：{mode}
        燈號：{light} - {advice}
        勝率分數：{engine['win_score']}
        因子分數：{engine['factor_scores']}
        核心數據：{m}
        否決條件：{engine['hard_flags']}
        交易計畫：{trade_plan}
        HITL：{advanced}
        請輸出：1.投審結論 2.白馬/黑馬因子解讀 3.進出場計畫 4.否決條件 5.風險控管。
        必須保留免責：不保證獲利，不構成投資建議。
        """
        try:
            model_names = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
            report = ""
            box = st.empty()
            for model_name in model_names:
                try:
                    response = ai_client.models.generate_content_stream(model=model_name, contents=prompt)
                    for chunk in response:
                        if getattr(chunk, "text", None):
                            report += chunk.text
                            box.markdown(report + "▌")
                    box.markdown(report)
                    report_md = build_report_markdown(symbol, engine, light, advice, trade_plan, report)
                    st.download_button("下載 Markdown 報告", report_md.encode("utf-8-sig"), f"{symbol}_wallwin_report.md", "text/markdown")
                    st.download_button("下載 PDF 報告", markdown_to_pdf_bytes(report_md), f"{symbol}_wallwin_report.pdf", "application/pdf")
                    st.success(f"✅ 成功透過 {model_name} 完成報告")
                    break
                except Exception as exc:
                    st.info(f"{model_name} 執行失敗：{exc}")
        except Exception as exc:
            st.error(f"AI 報告失敗：{exc}")
