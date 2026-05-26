import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import google.generativeai as genai


MIN_ANALYSIS_DAYS = 200
DAYTRADE_INTERVAL = "5m"
DAYTRADE_PERIOD = "5d"


def get_secret_value(name, default=""):
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return default


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
        else:
            st.error("密碼錯誤，請重新輸入。")
    st.stop()


def truthy_secret(name, default=False):
    value = get_secret_value(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "y", "on"}


def resolve_ai_api_key():
    allow_owner_key = truthy_secret("ALLOW_OWNER_KEY", default=False)
    owner_key = get_secret_value("GEMINI_API_KEY") if allow_owner_key else ""

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔑 AI 報告 API Key")
    if allow_owner_key and owner_key:
        st.sidebar.success("Owner Key 模式已啟用")
        return owner_key, "owner"

    user_key = st.sidebar.text_input(
        "Gemini API Key（由使用者自備）",
        type="password",
        help="Key 只保存在目前瀏覽器工作階段，不會寫入 GitHub 或 App 檔案。",
    ).strip()
    st.sidebar.caption("外部使用者若要產生 AI 報告，必須使用自己的 Gemini API Key。")
    return user_key, "user" if user_key else "missing"


def safe_float(val, default=0.0):
    try:
        if val is None or str(val).strip() == "":
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_last(series, default=0.0):
    try:
        value = series.dropna().iloc[-1]
        return safe_float(value, default)
    except (IndexError, AttributeError, ValueError, TypeError):
        return default


def pct_gap(price, base):
    if base and base > 0:
        return (price - base) / base * 100
    return 0.0


def score_bucket(score):
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def calc_valuation_score(peg, pb, dividend_yield):
    valuation_score = 50
    if peg < 0.75:
        valuation_score += 25
    elif peg <= 1.2:
        valuation_score += 15
    elif peg < 999:
        valuation_score -= 15
    if 0 < pb < 1.5:
        valuation_score += 15
    if dividend_yield >= 3:
        valuation_score += 10
    return min(max(valuation_score, 0), 100)


def refresh_composite_score(m):
    m["valuation_score"] = calc_valuation_score(
        m["peg"], m["pb"], m["dividend_yield"]
    )
    m["technical_score"] = round(
        m["trend_score"] * 0.35
        + m["momentum_score"] * 0.25
        + m["risk_score"] * 0.25
        + m["valuation_score"] * 0.15,
        1,
    )
    m["score_bucket"] = score_bucket(m["technical_score"])
    return m


def calculate_daytrade_matrix(intraday_df):
    if intraday_df is None or intraday_df.empty:
        return {"available": False, "reason": "查無 5 分鐘線資料"}

    df = intraday_df.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if df.empty or len(df) < 30:
        return {"available": False, "reason": "5 分鐘線資料不足，無法建立當沖判讀"}

    if isinstance(df.index, pd.DatetimeIndex):
        latest_day = df.index.max().date()
        session = df[df.index.date == latest_day].copy()
    else:
        session = df.tail(60).copy()

    if len(session) < 12:
        return {"available": False, "reason": "當日盤中資料不足，請於開盤後再評估"}

    close = session["Close"]
    high = session["High"]
    low = session["Low"]
    volume = session["Volume"]
    price = safe_float(close.iloc[-1])
    open_price = safe_float(session["Open"].iloc[0])
    day_high = safe_float(high.max())
    day_low = safe_float(low.min())
    day_volume = safe_float(volume.sum())
    avg_bar_volume = safe_float(df["Volume"].rolling(window=20).mean().dropna().tail(20).mean())
    last_bar_volume = safe_float(volume.iloc[-1])
    intraday_rvol = last_bar_volume / avg_bar_volume if avg_bar_volume > 0 else 0.0

    typical_price = (high + low + close) / 3
    cumulative_volume = volume.cumsum()
    intraday_vwap = safe_float((typical_price * volume).cumsum().iloc[-1] / cumulative_volume.iloc[-1]) if cumulative_volume.iloc[-1] > 0 else 0.0
    ema9 = safe_last(close.ewm(span=9, adjust=False).mean())
    ema21 = safe_last(close.ewm(span=21, adjust=False).mean())
    rsi_5m = safe_last(ta.momentum.RSIIndicator(close=close, window=14).rsi(), default=50.0)
    macd_diff_5m = safe_last(ta.trend.MACD(close=close).macd_diff())
    atr_5m = safe_last(ta.volatility.AverageTrueRange(high=high, low=low, close=close).average_true_range())
    atr_5m_pct = atr_5m / price * 100 if price > 0 else 0.0

    open_range = session.head(6)
    orb_high = safe_float(open_range["High"].max())
    orb_low = safe_float(open_range["Low"].min())
    range_pct = pct_gap(day_high, day_low)
    vwap_gap_pct = pct_gap(price, intraday_vwap)

    long_bias_score = 0
    if price > intraday_vwap > 0:
        long_bias_score += 25
    if ema9 > ema21 > 0:
        long_bias_score += 20
    if price > orb_high > 0:
        long_bias_score += 25
    if macd_diff_5m > 0:
        long_bias_score += 15
    if 45 <= rsi_5m <= 72:
        long_bias_score += 15

    short_bias_score = 0
    if 0 < price < intraday_vwap:
        short_bias_score += 25
    if 0 < ema9 < ema21:
        short_bias_score += 20
    if 0 < price < orb_low:
        short_bias_score += 25
    if macd_diff_5m < 0:
        short_bias_score += 15
    if 28 <= rsi_5m <= 55:
        short_bias_score += 15

    return {
        "available": True,
        "price": price,
        "open": open_price,
        "day_high": day_high,
        "day_low": day_low,
        "day_volume": day_volume,
        "intraday_rvol": intraday_rvol,
        "intraday_vwap": intraday_vwap,
        "vwap_gap_pct": vwap_gap_pct,
        "ema9": ema9,
        "ema21": ema21,
        "rsi_5m": rsi_5m,
        "macd_diff_5m": macd_diff_5m,
        "atr_5m": atr_5m,
        "atr_5m_pct": atr_5m_pct,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "range_pct": range_pct,
        "long_bias_score": long_bias_score,
        "short_bias_score": short_bias_score,
        "bar_count": len(session),
    }


def run_signal_backtest(df, max_atr=5.0, min_rvol=1.2, holding_days=20):
    df = df.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(df) < 120:
        return None, {"狀態": "資料不足，至少需要 120 個交易日"}

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    rsi = ta.momentum.RSIIndicator(close=close).rsi()
    macd_diff = ta.trend.MACD(close=close).macd_diff()
    atr_pct = ta.volatility.AverageTrueRange(high=high, low=low, close=close).average_true_range() / close * 100
    rvol = volume / volume.rolling(20).mean()

    signal = (
        (close > ma20)
        & (close > ma50)
        & ((ma200.isna()) | (close > ma200))
        & (rsi.between(45, 70))
        & (macd_diff > 0)
        & (atr_pct <= max_atr)
        & (rvol >= min_rvol)
    )

    trades = []
    last_exit_idx = -1
    for idx in range(60, len(df) - holding_days):
        if idx <= last_exit_idx or not bool(signal.iloc[idx]):
            continue
        entry = safe_float(close.iloc[idx])
        future = close.iloc[idx + 1 : idx + holding_days + 1]
        if future.empty or entry <= 0:
            continue
        exit_price = safe_float(future.iloc[-1])
        max_gain = (safe_float(future.max()) - entry) / entry * 100
        max_drawdown = (safe_float(future.min()) - entry) / entry * 100
        ret = (exit_price - entry) / entry * 100
        trades.append(
            {
                "進場日": df.index[idx].date() if hasattr(df.index[idx], "date") else df.index[idx],
                "進場價": round(entry, 2),
                "出場價": round(exit_price, 2),
                "持有日": holding_days,
                "報酬率%": round(ret, 2),
                "期間最大漲幅%": round(max_gain, 2),
                "期間最大回撤%": round(max_drawdown, 2),
            }
        )
        last_exit_idx = idx + holding_days

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return trades_df, {"狀態": "回測期間沒有符合條件的訊號"}

    returns = trades_df["報酬率%"]
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    stats = {
        "交易次數": len(trades_df),
        "勝率%": round(len(wins) / len(trades_df) * 100, 1),
        "平均報酬%": round(returns.mean(), 2),
        "中位數報酬%": round(returns.median(), 2),
        "最佳單筆%": round(returns.max(), 2),
        "最差單筆%": round(returns.min(), 2),
        "平均最大回撤%": round(trades_df["期間最大回撤%"].mean(), 2),
        "盈虧比": round(abs(wins.mean() / losses.mean()), 2) if not wins.empty and not losses.empty and losses.mean() != 0 else 0,
    }
    return trades_df, stats


def parse_watchlist(raw_text):
    tokens = raw_text.replace("\n", ",").replace("，", ",").split(",")
    return [token.strip().upper() for token in tokens if token.strip()]


# --- 1. 核心運算引擎：投審 + 主流技術分析版 ---
def calculate_quant_matrix(ticker_obj, df, advanced_df, target_symbol):
    try:
        info = ticker_obj.info or {}
    except Exception:
        info = {}

    df = df.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    pe = safe_float(info.get("trailingPE"))
    pb = safe_float(info.get("priceToBook"))
    eps_g = safe_float(info.get("earningsQuarterlyGrowth")) * 100
    beta = safe_float(info.get("beta"), default=1.0)
    dividend_yield = safe_float(info.get("dividendYield")) * 100

    peg = (pe / eps_g) if (eps_g > 0 and pe > 0) else 999.0
    close_price = safe_float(close.iloc[-1])
    last_volume = safe_float(volume.iloc[-1])

    ma20 = close.rolling(window=20).mean()
    ma50 = close.rolling(window=50).mean()
    ma200 = close.rolling(window=200).mean()
    vol_20ma = volume.rolling(window=20).mean()

    rvol = last_volume / safe_last(vol_20ma) if safe_last(vol_20ma) > 0 else 0.0
    low_min_20 = low.tail(20).min()
    vcp = ((high.tail(20).max() - low_min_20) / low_min_20 * 100) if low_min_20 > 0 else 0.0
    range_5 = pct_gap(high.tail(5).max(), low.tail(5).min())
    range_20 = pct_gap(high.tail(20).max(), low.tail(20).min())
    contraction_ratio = range_5 / range_20 if range_20 > 0 else 1.0

    vwap = safe_last(
        ta.volume.VolumeWeightedAveragePrice(
            high=high, low=low, close=close, volume=volume
        ).volume_weighted_average_price()
    )
    atr = ta.volatility.AverageTrueRange(high=high, low=low, close=close).average_true_range()
    atr_pct = safe_last(atr) / close_price * 100 if close_price > 0 else 0.0
    rsi = safe_last(ta.momentum.RSIIndicator(close=close).rsi(), default=50.0)
    macd_diff = safe_last(ta.trend.MACD(close=close).macd_diff())
    adx = safe_last(ta.trend.ADXIndicator(high=high, low=low, close=close).adx())
    obv = ta.volume.OnBalanceVolumeIndicator(close=close, volume=volume).on_balance_volume()
    obv_slope = safe_last(obv.diff(20))
    bb = ta.volatility.BollingerBands(close=close)
    bb_high = safe_last(bb.bollinger_hband())
    bb_low = safe_last(bb.bollinger_lband())
    bb_width = ((bb_high - bb_low) / close_price * 100) if close_price > 0 else 0.0

    ma20_v = safe_last(ma20)
    ma50_v = safe_last(ma50)
    ma200_v = safe_last(ma200)
    dollar_volume = close_price * last_volume

    trend_score = 0
    if close_price > ma20_v > 0:
        trend_score += 15
    if close_price > ma50_v > 0:
        trend_score += 20
    if ma50_v > ma200_v > 0:
        trend_score += 20
    if close_price > ma200_v > 0:
        trend_score += 20
    if adx >= 20:
        trend_score += 10
    if macd_diff > 0:
        trend_score += 15

    momentum_score = 0
    if 45 <= rsi <= 70:
        momentum_score += 30
    elif 35 <= rsi < 45 or 70 < rsi <= 78:
        momentum_score += 15
    if rvol >= 1.5:
        momentum_score += 25
    if obv_slope > 0:
        momentum_score += 20
    if close_price >= vwap:
        momentum_score += 15
    if contraction_ratio <= 0.55:
        momentum_score += 10

    risk_score = 100
    if atr_pct > 5:
        risk_score -= 25
    if atr_pct > 8:
        risk_score -= 25
    if last_volume < 200000:
        risk_score -= 30
    if ma50_v > 0 and pct_gap(close_price, ma50_v) > 20:
        risk_score -= 20
    if beta > 1.8:
        risk_score -= 10
    risk_score = max(risk_score, 0)

    valuation_score = calc_valuation_score(peg, pb, dividend_yield)

    technical_score = round(
        trend_score * 0.35 + momentum_score * 0.25 + risk_score * 0.25 + valuation_score * 0.15,
        1,
    )

    m = {
        "price": close_price,
        "volume": last_volume,
        "dollar_volume": dollar_volume,
        "pe": pe,
        "pb": pb,
        "beta": beta,
        "peg": peg,
        "eps_g": eps_g,
        "dividend_yield": dividend_yield,
        "rvol": rvol,
        "vcp": vcp,
        "contraction_ratio": contraction_ratio,
        "vwap": vwap,
        "atr_pct": atr_pct,
        "rsi": rsi,
        "macd_diff": macd_diff,
        "adx": adx,
        "bb_width": bb_width,
        "ma20": ma20_v,
        "ma50": ma50_v,
        "ma200": ma200_v,
        "ma50_gap_pct": pct_gap(close_price, ma50_v),
        "ma200_gap_pct": pct_gap(close_price, ma200_v),
        "trend_score": trend_score,
        "momentum_score": momentum_score,
        "risk_score": risk_score,
        "valuation_score": valuation_score,
        "technical_score": technical_score,
        "score_bucket": score_bucket(technical_score),
        "data_points": len(df),
    }

    m["advanced"] = {}
    if advanced_df is not None:
        try:
            matched_row = advanced_df[advanced_df["股號"].astype(str) == str(target_symbol)]
            if not matched_row.empty:
                row_dict = matched_row.iloc[0].to_dict()
                row_dict.pop("股號", None)
                m["advanced"] = {str(k): v for k, v in row_dict.items() if pd.notna(v)}
            else:
                st.sidebar.warning(f"⚠️ 降規模式：CSV 中找不到標的 {target_symbol}")
        except Exception as e:
            st.sidebar.error(f"❌ CSV 解析失敗: {e}")

    return m


def build_investment_audit(
    m,
    mode,
    strategy,
    min_volume,
    max_atr,
    r_thresh,
    v_thresh,
    trading_style="波段/投資",
    daytrade=None,
    daytrade_direction="做多",
    daytrade_min_volume=500000,
    daytrade_min_rvol=1.5,
    daytrade_max_atr_5m=1.2,
):
    items = []

    def add(name, passed, detail, severity="hard"):
        items.append(
            {
                "name": name,
                "passed": passed,
                "detail": detail,
                "severity": severity,
            }
        )

    add(
        "資料完整性",
        m["data_points"] >= MIN_ANALYSIS_DAYS,
        f"{m['data_points']} 日資料；投審基準建議至少 {MIN_ANALYSIS_DAYS} 日",
        "soft",
    )
    add(
        "流動性門檻",
        m["volume"] >= min_volume,
        f"成交量 {m['volume'] / 1000:,.0f} 張，門檻 {min_volume / 1000:,.0f} 張",
        "hard",
    )
    add(
        "波動風險",
        m["atr_pct"] <= max_atr,
        f"ATR {m['atr_pct']:.2f}%，上限 {max_atr:.2f}%",
        "hard",
    )
    add(
        "長線趨勢",
        m["price"] >= m["ma200"] if m["ma200"] > 0 else False,
        f"價格相對 MA200：{m['ma200_gap_pct']:.2f}%",
        "hard" if mode == "黑馬潛力股 (轉機/突破)" else "soft",
    )
    add(
        "中期延伸風險",
        m["ma50_gap_pct"] <= 20,
        f"價格相對 MA50：{m['ma50_gap_pct']:.2f}%",
        "soft",
    )

    if trading_style == "當沖":
        if not daytrade or not daytrade.get("available"):
            add(
                "當沖資料",
                False,
                daytrade.get("reason", "缺少 5 分鐘線資料") if daytrade else "缺少 5 分鐘線資料",
                "hard",
            )
        else:
            is_long = daytrade_direction == "做多"
            bias_score = daytrade["long_bias_score"] if is_long else daytrade["short_bias_score"]
            vwap_ok = daytrade["price"] > daytrade["intraday_vwap"] if is_long else daytrade["price"] < daytrade["intraday_vwap"]
            orb_ok = daytrade["price"] > daytrade["orb_high"] if is_long else daytrade["price"] < daytrade["orb_low"]
            ema_ok = daytrade["ema9"] > daytrade["ema21"] if is_long else daytrade["ema9"] < daytrade["ema21"]
            rsi_ok = 45 <= daytrade["rsi_5m"] <= 72 if is_long else 28 <= daytrade["rsi_5m"] <= 55

            add(
                "當沖流動性",
                daytrade["day_volume"] >= daytrade_min_volume,
                f"盤中量 {daytrade['day_volume'] / 1000:,.0f} 張，門檻 {daytrade_min_volume / 1000:,.0f} 張",
                "hard",
            )
            add(
                "5 分鐘量能",
                daytrade["intraday_rvol"] >= daytrade_min_rvol,
                f"5 分鐘 RVOL {daytrade['intraday_rvol']:.2f}x，門檻 {daytrade_min_rvol:.2f}x",
                "hard",
            )
            add(
                "VWAP 方向",
                vwap_ok,
                f"價格相對 VWAP：{daytrade['vwap_gap_pct']:.2f}%",
                "hard",
            )
            add(
                "開盤區間突破",
                orb_ok,
                f"ORB 高 {daytrade['orb_high']:.2f} / 低 {daytrade['orb_low']:.2f}",
                "hard",
            )
            add(
                "EMA 9/21 方向",
                ema_ok,
                f"EMA9 {daytrade['ema9']:.2f} / EMA21 {daytrade['ema21']:.2f}",
                "soft",
            )
            add(
                "5 分鐘 RSI",
                rsi_ok,
                f"RSI {daytrade['rsi_5m']:.1f}",
                "soft",
            )
            add(
                "5 分鐘波動上限",
                daytrade["atr_5m_pct"] <= daytrade_max_atr_5m,
                f"5 分鐘 ATR {daytrade['atr_5m_pct']:.2f}%，上限 {daytrade_max_atr_5m:.2f}%",
                "hard",
            )
            add(
                "當沖方向分數",
                bias_score >= 70,
                f"{daytrade_direction} 分數 {bias_score}/100",
                "hard",
            )
    elif strategy == "積極型 (動能/短線)":
        add(
            "突破確認",
            m["rvol"] >= r_thresh and m["vcp"] <= v_thresh and m["macd_diff"] > 0,
            f"RVOL {m['rvol']:.2f}x / VCP {m['vcp']:.2f}% / MACD diff {m['macd_diff']:.2f}",
            "hard",
        )
    elif strategy == "保守型 (防禦/股息)":
        add(
            "估值防線",
            (0 < m["pb"] <= 1.8) or m["dividend_yield"] >= 3,
            f"P/B {m['pb']:.2f} / 殖利率 {m['dividend_yield']:.2f}%",
            "hard",
        )
    else:
        add(
            "成長估值",
            m["peg"] <= 1.2,
            f"PEG {m['peg']:.2f}",
            "hard",
        )

    hard_failed = [x for x in items if not x["passed"] and x["severity"] == "hard"]
    soft_failed = [x for x in items if not x["passed"] and x["severity"] == "soft"]
    return items, hard_failed, soft_failed


# --- 2. 戰術燈號 ---
def get_traffic_light(
    m,
    mode,
    strategy,
    r_thresh,
    v_thresh,
    min_volume,
    max_atr,
    trading_style="波段/投資",
    daytrade=None,
    daytrade_direction="做多",
    daytrade_min_volume=500000,
    daytrade_min_rvol=1.5,
    daytrade_max_atr_5m=1.2,
):
    audit_items, hard_failed, soft_failed = build_investment_audit(
        m,
        mode,
        strategy,
        min_volume,
        max_atr,
        r_thresh,
        v_thresh,
        trading_style,
        daytrade,
        daytrade_direction,
        daytrade_min_volume,
        daytrade_min_rvol,
        daytrade_max_atr_5m,
    )

    if hard_failed:
        if trading_style == "當沖":
            return "🔴 紅燈", "未通過當沖硬門檻，禁止追價進場", audit_items
        return "🔴 紅燈", "未通過投審硬門檻，暫不啟動新倉位", audit_items
    if trading_style == "當沖":
        score = daytrade["long_bias_score"] if daytrade_direction == "做多" else daytrade["short_bias_score"]
        if score >= 85 and not soft_failed:
            return "🟢 綠燈", "當沖方向、量能與 VWAP 共振，可依紀律小部位執行", audit_items
        return "🔵 藍燈", "當沖條件可追蹤，需等待下一根 5 分鐘 K 確認", audit_items
    if m["technical_score"] >= 75 and not soft_failed:
        return "🟢 綠燈", "投審與技術共振，可進入分批執行清單", audit_items
    if m["technical_score"] >= 60:
        return "🔵 藍燈", "條件接近成熟，等待突破或估值修正確認", audit_items
    return "🟡 黃燈", "訊號不足，僅保留追蹤，不建議追價", audit_items


def render_audit_table(audit_items):
    audit_df = pd.DataFrame(audit_items)
    audit_df["結果"] = audit_df["passed"].map({True: "PASS", False: "FAIL"})
    audit_df["類型"] = audit_df["severity"].map({"hard": "硬門檻", "soft": "觀察項"})
    st.dataframe(
        audit_df[["結果", "類型", "name", "detail"]].rename(
            columns={"name": "審核項目", "detail": "判讀"}
        ),
        use_container_width=True,
        hide_index=True,
    )


def build_trade_plan(m, strategy, trading_style="波段/投資", daytrade=None, daytrade_direction="做多"):
    if trading_style == "當沖" and daytrade and daytrade.get("available"):
        entry = daytrade["price"]
        is_long = daytrade_direction == "做多"
        atr_buffer = max(daytrade["atr_5m"] * 1.2, entry * 0.003)
        if is_long:
            stop = min(daytrade["intraday_vwap"], daytrade["orb_low"], entry - atr_buffer)
            risk = max(entry - stop, 0.01)
            target_1 = entry + risk * 1.5
            target_2 = entry + risk * 2.5
        else:
            stop = max(daytrade["intraday_vwap"], daytrade["orb_high"], entry + atr_buffer)
            risk = max(stop - entry, 0.01)
            target_1 = entry - risk * 1.5
            target_2 = entry - risk * 2.5

        return {
            "entry": entry,
            "stop": stop,
            "target_1": target_1,
            "target_2": target_2,
            "position_hint": "當沖單筆風險 0.25%-0.5%，禁止攤平，收盤前清倉",
            "rr": abs(target_1 - entry) / risk,
        }

    entry = m["price"]
    stop_by_atr = entry * (1 - max(m["atr_pct"] * 1.5, 3.0) / 100)
    support_stop = m["ma50"] if m["ma50"] > 0 else stop_by_atr
    stop = min(stop_by_atr, support_stop)
    risk = max(entry - stop, 0.01)
    target_1 = entry + risk * 2
    target_2 = entry + risk * 3

    if strategy == "保守型 (防禦/股息)":
        position_hint = "單筆風險 0.5% 以內，分 3 批建立"
    elif strategy == "積極型 (動能/短線)":
        position_hint = "單筆風險 1.0% 以內，突破確認後分 2 批"
    else:
        position_hint = "單筆風險 0.75% 以內，回測支撐分批"

    return {
        "entry": entry,
        "stop": stop,
        "target_1": target_1,
        "target_2": target_2,
        "position_hint": position_hint,
        "rr": (target_1 - entry) / risk,
    }


# --- 3. 頁面初始化 ---
st.set_page_config(page_title="WallWin Gem 量化系統", layout="wide")
st.title("🛡️ WallWin Gem 投審量化指揮中心")
st.caption("投資審核流程 + 主流技術分析共識模型；輸出為研究輔助，不構成投資建議。")
require_app_password()

# --- 4. 側邊欄：戰略控制台 ---
st.sidebar.header("⚙️ 戰略控制台")
ai_api_key, ai_key_source = resolve_ai_api_key()
stock_target = st.sidebar.text_input("🎯 目標股號", "2206.TW")
trading_style = st.sidebar.radio("交易週期", ["波段/投資", "當沖"], horizontal=True)
mode_select = st.sidebar.radio("市場定調", ["白馬股 (價值/已驗證)", "黑馬潛力股 (轉機/突破)"])
strategy_select = st.sidebar.selectbox("戰略模組", ["穩健型 (合理成長)", "保守型 (防禦/股息)", "積極型 (動能/短線)"])

st.sidebar.markdown("---")

with st.sidebar.expander("🎚️ 投審與技術參數", expanded=True):
    min_volume = st.slider("最低成交量門檻（張）", 50, 2000, 200, 50) * 1000
    max_atr = st.slider("ATR 風險上限 (%)", 2.0, 12.0, 5.0, 0.5)
    r_thresh = st.slider("RVOL 爆量閾值", 1.0, 5.0, 2.0, 0.1)
    v_thresh = st.slider("VCP 壓縮限度 (%)", 1.0, 20.0, 8.0, 0.5)

    if r_thresh < 1.5:
        st.warning("⚠️ RVOL 閾值過低，易產生假突破訊號。")
    if v_thresh > 12.0:
        st.warning("⚠️ VCP 容忍度過高，會弱化波動收斂判讀。")

if trading_style == "當沖":
    with st.sidebar.expander("⚡ 當沖投審設定", expanded=True):
        daytrade_direction = st.radio("當沖方向", ["做多", "放空"], horizontal=True)
        daytrade_min_volume = st.slider("盤中成交量門檻（張）", 100, 5000, 500, 100) * 1000
        daytrade_min_rvol = st.slider("5 分鐘 RVOL 門檻", 1.0, 5.0, 1.8, 0.1)
        daytrade_max_atr_5m = st.slider("5 分鐘 ATR 上限 (%)", 0.2, 3.0, 1.2, 0.1)
        st.caption("當沖模式使用 5 分鐘線、VWAP、EMA9/21、RSI、MACD 與開盤區間突破檢核。")
else:
    daytrade_direction = "做多"
    daytrade_min_volume = 500000
    daytrade_min_rvol = 1.8
    daytrade_max_atr_5m = 1.2

st.sidebar.subheader("📁 HITL 進階私房數據")
uploaded_file = st.sidebar.file_uploader("上傳 .csv 檔案 (解鎖進階分析)", type="csv")
advanced_data = None
if uploaded_file:
    advanced_data = pd.read_csv(uploaded_file)
    st.sidebar.success("✅ 私房數據已掛載")
else:
    st.sidebar.warning("⚠️ 降規模式：未掛載 CSV")

st.sidebar.markdown("---")

st.sidebar.subheader("🛠️ HITL 基礎人工校準")
manual_override = st.sidebar.toggle("啟用 PEG 數據覆蓋")
hitl_peg = 999.0
if manual_override:
    hitl_peg = st.sidebar.number_input("手動修正 PEG 數據", 0.0, 10.0, 1.2, 0.1)

st.sidebar.markdown("<br>", unsafe_allow_html=True)
analyze_button = st.sidebar.button("🚀 啟動深度量化解析", use_container_width=True, type="primary")

st.sidebar.markdown("---")
st.sidebar.subheader("📡 Watchlist 多檔掃描")
watchlist_symbols = st.sidebar.text_area(
    "股票清單（逗號或換行分隔）",
    "2330.TW, 2317.TW, 2454.TW, 2206.TW",
    height=90,
)
scan_button = st.sidebar.button("📡 掃描 Watchlist", use_container_width=True)

if scan_button:
    symbols = parse_watchlist(watchlist_symbols)
    if not symbols:
        st.error("請至少輸入一個股票代號。")
        st.stop()
    if len(symbols) > 20:
        st.error("為避免公開 App 被濫用，Watchlist 單次最多掃描 20 檔。")
        st.stop()

    rows = []
    progress = st.progress(0, text="Watchlist 掃描中")
    for idx, symbol in enumerate(symbols, start=1):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1y")
            if hist.empty or len(hist) < 60:
                rows.append({"股號": symbol, "狀態": "資料不足"})
                continue
            m = calculate_quant_matrix(ticker, hist, advanced_data, symbol)
            light, advice, audit_items = get_traffic_light(
                m,
                mode_select,
                strategy_select,
                r_thresh,
                v_thresh,
                min_volume,
                max_atr,
                "波段/投資",
            )
            failed_hard = sum(1 for item in audit_items if not item["passed"] and item["severity"] == "hard")
            rows.append(
                {
                    "股號": symbol,
                    "燈號": light,
                    "技術分數": m["technical_score"],
                    "分級": m["score_bucket"],
                    "價格": round(m["price"], 2),
                    "成交量(張)": round(m["volume"] / 1000, 0),
                    "RVOL": round(m["rvol"], 2),
                    "VCP%": round(m["vcp"], 2),
                    "RSI": round(m["rsi"], 1),
                    "ATR%": round(m["atr_pct"], 2),
                    "硬門檻失敗": failed_hard,
                    "摘要": advice,
                    "狀態": "OK",
                }
            )
        except Exception as e:
            rows.append({"股號": symbol, "狀態": f"錯誤：{e}"})
        progress.progress(idx / len(symbols), text=f"Watchlist 掃描中：{idx}/{len(symbols)}")

    progress.empty()
    result_df = pd.DataFrame(rows)
    if "技術分數" in result_df.columns:
        result_df = result_df.sort_values(["狀態", "硬門檻失敗", "技術分數"], ascending=[True, True, False])
    st.subheader("📡 Watchlist 多檔掃描結果")
    st.dataframe(result_df, use_container_width=True, hide_index=True)
    st.download_button(
        "下載 Watchlist CSV",
        result_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="wallwin_watchlist.csv",
        mime="text/csv",
    )

# --- 5. 運算與 UI 展示 ---
if analyze_button:
    with st.spinner(f"擷取 {stock_target} 數據中..."):
        ticker = yf.Ticker(stock_target)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 60:
            st.error("❌ 查無足夠資料或標的已下市")
            st.stop()

        m = calculate_quant_matrix(ticker, hist, advanced_data, stock_target)
        daytrade = None
        if trading_style == "當沖":
            intraday_hist = ticker.history(period=DAYTRADE_PERIOD, interval=DAYTRADE_INTERVAL)
            daytrade = calculate_daytrade_matrix(intraday_hist)

        if manual_override:
            m["peg"] = hitl_peg
            m = refresh_composite_score(m)
            st.warning(f"🛠️ HITL 介入：已手動將 PEG 覆蓋為 {hitl_peg}")

        light_color, advice, audit_items = get_traffic_light(
            m,
            mode_select,
            strategy_select,
            r_thresh,
            v_thresh,
            min_volume,
            max_atr,
            trading_style,
            daytrade,
            daytrade_direction,
            daytrade_min_volume,
            daytrade_min_rvol,
            daytrade_max_atr_5m,
        )
        trade_plan = build_trade_plan(m, strategy_select, trading_style, daytrade, daytrade_direction)

        st.info(
            f"**最新收盤價：`{m['price']:.2f}`** │ "
            f"最新成交量：`{m['volume'] / 1000:,.0f}` 張 │ "
            f"技術共識分數：`{m['technical_score']:.1f}` / 100（{m['score_bucket']}）"
        )

        if m["volume"] < min_volume:
            st.error("🩸 【流動性警告】：成交量未達投審門檻，滑價與操縱風險偏高。")
        if m["atr_pct"] > max_atr:
            st.warning(f"🌪️ 【高波動警告】：ATR {m['atr_pct']:.2f}% 已超過風險上限。")

        col1, col2 = st.columns([2, 1])
        with col1:
            st.line_chart(hist[["Close"]].tail(160))
        with col2:
            st.subheader("核心量化指標")
            st.metric("P/E", f"{m['pe']:.2f}")
            st.metric("PEG", f"{m['peg']:.2f}", delta="手動覆蓋" if manual_override else ("數據缺失" if m["peg"] == 999.0 else None))
            st.metric("RVOL", f"{m['rvol']:.2f}x")
            st.metric("VCP", f"{m['vcp']:.2f}%")
            st.metric("RSI", f"{m['rsi']:.1f}")
            st.metric("ADX", f"{m['adx']:.1f}")

        if trading_style == "當沖":
            tab_audit, tab_tech, tab_daytrade, tab_backtest, tab_plan, tab_ai = st.tabs(["投審檢核", "技術面", "當沖", "回測", "交易計畫", "AI 報告"])
        else:
            tab_audit, tab_tech, tab_backtest, tab_plan, tab_ai = st.tabs(["投審檢核", "技術面", "回測", "交易計畫", "AI 報告"])

        with tab_audit:
            st.subheader("🚦 戰術判定燈號")
            st.write(f"**{light_color}**：{advice}")
            render_audit_table(audit_items)

            if m["advanced"]:
                st.markdown("---")
                st.markdown("**💎 成功匯入之機構數據：**")
                for k, v in m["advanced"].items():
                    st.write(f"- {k}: **{v}**")

        with tab_tech:
            tech_cols = st.columns(4)
            tech_cols[0].metric("MA20", f"{m['ma20']:.2f}")
            tech_cols[1].metric("MA50", f"{m['ma50']:.2f}", f"{m['ma50_gap_pct']:.2f}%")
            tech_cols[2].metric("MA200", f"{m['ma200']:.2f}", f"{m['ma200_gap_pct']:.2f}%")
            tech_cols[3].metric("BB Width", f"{m['bb_width']:.2f}%")
            st.write(
                f"MACD Diff：**{m['macd_diff']:.2f}** │ "
                f"VWAP：**{m['vwap']:.2f}** │ "
                f"ATR：**{m['atr_pct']:.2f}%** │ "
                f"VCP 收斂比：**{m['contraction_ratio']:.2f}**"
            )

        if trading_style == "當沖":
            with tab_daytrade:
                st.subheader("⚡ 當沖投審分析")
                if not daytrade or not daytrade.get("available"):
                    st.error(daytrade.get("reason", "查無當沖資料") if daytrade else "查無當沖資料")
                else:
                    day_cols = st.columns(4)
                    day_cols[0].metric("盤中價", f"{daytrade['price']:.2f}", f"{daytrade['vwap_gap_pct']:.2f}% vs VWAP")
                    day_cols[1].metric("5m RVOL", f"{daytrade['intraday_rvol']:.2f}x")
                    day_cols[2].metric("5m RSI", f"{daytrade['rsi_5m']:.1f}")
                    day_cols[3].metric("5m ATR", f"{daytrade['atr_5m_pct']:.2f}%")

                    st.write(
                        f"方向：**{daytrade_direction}** │ "
                        f"VWAP：**{daytrade['intraday_vwap']:.2f}** │ "
                        f"EMA9/21：**{daytrade['ema9']:.2f} / {daytrade['ema21']:.2f}** │ "
                        f"MACD Diff：**{daytrade['macd_diff_5m']:.2f}**"
                    )
                    st.write(
                        f"開盤區間高低：**{daytrade['orb_high']:.2f} / {daytrade['orb_low']:.2f}** │ "
                        f"當日高低：**{daytrade['day_high']:.2f} / {daytrade['day_low']:.2f}** │ "
                        f"盤中量：**{daytrade['day_volume'] / 1000:,.0f} 張**"
                    )
                    st.progress(
                        min(
                            (daytrade["long_bias_score"] if daytrade_direction == "做多" else daytrade["short_bias_score"]) / 100,
                            1.0,
                        ),
                        text=f"{daytrade_direction} 當沖方向分數",
                    )

        with tab_backtest:
            st.subheader("📈 簡易訊號回測")
            backtest_days = st.slider("持有天數", 5, 60, 20, 5)
            backtest_rvol = st.slider("回測 RVOL 門檻", 1.0, 3.0, 1.2, 0.1)
            trades_df, stats = run_signal_backtest(hist, max_atr=max_atr, min_rvol=backtest_rvol, holding_days=backtest_days)

            if trades_df is None or trades_df.empty:
                st.warning(stats.get("狀態", "沒有可顯示的回測結果"))
            else:
                stat_cols = st.columns(4)
                stat_cols[0].metric("交易次數", stats["交易次數"])
                stat_cols[1].metric("勝率", f"{stats['勝率%']:.1f}%")
                stat_cols[2].metric("平均報酬", f"{stats['平均報酬%']:.2f}%")
                stat_cols[3].metric("最差單筆", f"{stats['最差單筆%']:.2f}%")
                st.write(
                    f"中位數報酬：**{stats['中位數報酬%']:.2f}%** │ "
                    f"最佳單筆：**{stats['最佳單筆%']:.2f}%** │ "
                    f"平均最大回撤：**{stats['平均最大回撤%']:.2f}%** │ "
                    f"盈虧比：**{stats['盈虧比']:.2f}**"
                )
                st.dataframe(trades_df.tail(30), use_container_width=True, hide_index=True)
                st.download_button(
                    "下載回測交易明細 CSV",
                    trades_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{stock_target}_backtest.csv",
                    mime="text/csv",
                )

        with tab_plan:
            st.subheader("📌 執行框架")
            plan_cols = st.columns(4)
            plan_cols[0].metric("觀察/進場價", f"{trade_plan['entry']:.2f}")
            plan_cols[1].metric("風控停損", f"{trade_plan['stop']:.2f}")
            plan_cols[2].metric("目標一", f"{trade_plan['target_1']:.2f}")
            plan_cols[3].metric("目標二", f"{trade_plan['target_2']:.2f}")
            st.write(f"部位建議：**{trade_plan['position_hint']}**")
            st.write(f"第一目標風報比：約 **{trade_plan['rr']:.1f}R**")

        with tab_ai:
            st.subheader("🧠 決策大腦深度解析 (Gemini AI)")
            if not ai_api_key:
                st.warning("🔒 AI 報告已鎖定：請在左側輸入自己的 Gemini API Key。未輸入 Key 時，本 App 不會呼叫 Gemini，也不會消耗部署者額度。")
                st.stop()

            genai.configure(api_key=ai_api_key)
            if ai_key_source == "user":
                st.info("目前使用：使用者自備 Gemini API Key。此 Key 不會寫入 GitHub 或 Streamlit Secrets。")
            else:
                st.warning("目前使用：Owner Gemini API Key。若要開放外部使用，請不要啟用 ALLOW_OWNER_KEY。")

            data_status = "【完全體：已融合 BOSS 上傳之 CSV 機構數據】" if m["advanced"] else "【降規模式：缺乏高階基本面數據，請提醒 BOSS 上傳】"
            prompt = f"""
            你是一位華爾街投資委員會研究員與技術分析師。狀態：{data_status}。
            請用繁體中文輸出投研審核報告，且不要承諾報酬。

            目標：{stock_target}
            交易週期：{trading_style}
            當沖方向：{daytrade_direction if trading_style == '當沖' else '不適用'}
            市場定調：{mode_select}
            戰略模組：{strategy_select}
            燈號：{light_color} - {advice}
            投審檢核：{audit_items}
            當沖 5 分鐘線數據：{daytrade if trading_style == '當沖' else '不適用'}
            核心量化數據：
            股價 {m['price']:.2f}, P/E {m['pe']:.2f}, PEG {m['peg']:.2f}, P/B {m['pb']:.2f},
            EPS 成長 {m['eps_g']:.2f}%, 殖利率 {m['dividend_yield']:.2f}%,
            RVOL {m['rvol']:.2f}, VCP {m['vcp']:.2f}%, VWAP {m['vwap']:.2f},
            RSI {m['rsi']:.2f}, ADX {m['adx']:.2f}, MACD diff {m['macd_diff']:.2f},
            MA50 gap {m['ma50_gap_pct']:.2f}%, MA200 gap {m['ma200_gap_pct']:.2f}%,
            ATR {m['atr_pct']:.2f}%, 技術共識分數 {m['technical_score']:.1f}/100。
            執行框架：{trade_plan}
            BOSS CSV 私房數據：{m['advanced']}

            絕對約束：
            1. 必須全篇使用繁體中文，嚴禁簡體字。
            2. 嚴格依照「1.投審結論、2.關鍵依據、3.技術面判讀、4.執行計畫、5.風險與否決條件」五段結構。
            3. 若任一硬門檻未通過，必須明確寫出「暫不啟動新倉位」。
            4. 若交易週期為當沖，必須明確寫出「收盤前清倉、禁止攤平、嚴守停損」。
            """

            try:
                available_models = [
                    md.name
                    for md in genai.list_models()
                    if "generateContent" in md.supported_generation_methods
                    and "gemini" in md.name.lower()
                    and "vision" not in md.name.lower()
                    and "robotics" not in md.name.lower()
                    and "tts" not in md.name.lower()
                ]
                target_models = sorted(
                    [md for md in available_models if "1.5" in md or "2.0" in md or "2.5" in md],
                    key=lambda x: (0 if "flash" in x.lower() else 1),
                )[:3]

                success = False
                error_logs = []
                full_report = ""

                for model_name in target_models:
                    try:
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(prompt, stream=True)
                        res_box = st.empty()
                        full_report = ""

                        for chunk in response:
                            if chunk.parts:
                                full_report += chunk.text
                                res_box.markdown(full_report + "▌")

                        res_box.markdown(full_report)
                        success = True
                        st.success(f"✅ 成功透過 **{model_name}** 完成報告。")
                        break
                    except Exception as e:
                        error_logs.append(f"⚠️ **{model_name}** 執行異常：`{e}`")
                        continue

                if not success:
                    if len(full_report) > 50:
                        st.warning("⚠️ 報告結尾遭遇串流中斷，但主要內容已成功保存。")
                    else:
                        st.error("❌ 所有 AI 模型均拒絕連線。錯誤明細：")
                        for err in error_logs:
                            st.info(err)

            except Exception as e:
                st.error(f"❌ 系統連線基礎異常: {e}")
