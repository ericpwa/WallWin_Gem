import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import google.generativeai as genai

# --- 1. 核心運算引擎 ---
def calculate_quant_matrix(ticker_obj, df, advanced_df, rvol_threshold, vcp_threshold):
    info = ticker_obj.info
    # 基礎 API 數據
    m = {
        "price": df['Close'].iloc[-1],
        "volume": df['Volume'].iloc[-1],
        "pe": info.get('trailingPE', 0.0),
        "pb": info.get('priceToBook', 0.0),
        "beta": info.get('beta', 1.0),
        "peg": (info.get('trailingPE', 0.0) / (info.get('earningsQuarterlyGrowth', 0) * 100)) if info.get('earningsQuarterlyGrowth', 0) > 0 else 999.0,
        "rvol": df['Volume'].iloc[-1] / df['Volume'].rolling(window=20).mean().iloc[-1],
        "vcp": (df['High'].tail(5).max() - df['Low'].tail(5).min()) / df['Low'].tail(5).min() * 100,
        "vwap": ta.volume.VolumeWeightedAveragePrice(high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume']).volume_weighted_average_price().iloc[-1],
        "atr_pct": (ta.volatility.AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close']).average_true_range().iloc[-1] / df['Close'].iloc[-1]) * 100
    }
    
    # [HITL 2.0] 注入 BOSS 上傳的機構級數據
    m["advanced"] = {}
    if advanced_df is not None:
        try:
            # 比對股號，抓取第一筆匹配資料
            row = advanced_df[advanced_df['股號'] == stock_target].iloc[0]
            m["advanced"] = {
                "fcf": row.get('自由現金流量', '缺漏'),
                "roic": row.get('ROIC', '缺漏'),
                "f_score": row.get('F-Score 總分', '缺漏'),
                "foreign_pct": row.get('外資持股比率', '缺漏'),
                "it_pct": row.get('投信持股比率', '缺漏'),
                "op_trend": row.get('營業利益率趨勢', '缺漏')
            }
        except Exception:
            st.sidebar.error("❌ CSV 股號不匹配或格式有誤")
            
    return m

# --- 2. 戰術燈號 (整合降規邏輯) ---
def get_traffic_light(m, mode):
    # 範例邏輯：若有 F-Score 且 > 7 則加分
    score_bonus = 0
    if isinstance(m['advanced'].get('f_score'), (int, float)):
        if m['advanced']['f_score'] >= 7: score_bonus = 1
        
    if mode == "白馬股 (價值/已驗證)":
        if m['peg'] < 0.75 or score_bonus > 0: return "🟢 綠燈", "估值吸引力高或財務極度穩健"
        return "🔵 藍燈", "基礎指標持平，建議參考高階數據"
    else:
        if m['rvol'] > 2.0 and m['vcp'] < 5.0: return "🟢 綠燈", "爆量突破，動能確立"
        return "🔵 藍燈", "震盪蓄勢中"

# --- 3. UI 介面 ---
st.set_page_config(page_title="WallWin Gem 2.0", layout="wide")
st.title("🛡️ WallWin Gem 戰略指揮中心 (HITL 2.0)")

# API 設定
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("❌ 缺失 API Key"); st.stop()

# 側邊欄
st.sidebar.header("⚙️ 戰略控制台")
stock_target = st.sidebar.text_input("🎯 目標股號", "2317.TW")
mode_select = st.sidebar.radio("市場定調", ["白馬股 (價值/已驗證)", "黑馬潛力股 (轉機/突破)"])

st.sidebar.markdown("---")
st.sidebar.subheader("📁 機構級數據注入 (選填)")
uploaded_file = st.sidebar.file_uploader("上傳 .csv 檔案", type="csv")
advanced_data = None
if uploaded_file:
    advanced_data = pd.read_csv(uploaded_file)
    st.sidebar.success("✅ 機構數據已掛載")
else:
    st.sidebar.warning("⚠️ 執行降規模式：缺乏財報/籌碼數據")

analyze_button = st.sidebar.button("🚀 啟動深度量化解析", use_container_width=True)

# --- 4. 運算與輸出 ---
if analyze_button:
    with st.spinner("量子運算中..."):
        ticker = yf.Ticker(stock_target)
        hist = ticker.history(period="1y")
        if hist.empty: st.error("❌ 查無資料"); st.stop()
        
        m = calculate_quant_matrix(ticker, hist, advanced_data, 2.0, 5.0)
        
        # 數據面板
        st.info(f"**{stock_target} 現價：{m['price']:.2f}**")
        
        col1, col2 = st.columns([2, 1])
        with col1: st.line_chart(hist['Close'].tail(120))
        with col2:
            st.subheader("量化指標清單")
            st.write(f"P/E: {m['pe']:.2f} | PEG: {m['peg']:.2f}")
            st.write(f"RVOL: {m['rvol']:.2f} | VCP: {m['vcp']:.2f}%")
            if m['advanced']:
                st.markdown("---")
                st.markdown("**💎 已解鎖高級數據**")
                for k, v in m['advanced'].items(): st.write(f"{k}: {v}")
            
            light, adv = get_traffic_light(m, mode_select)
            st.metric("🚦 戰術判定", light, help=adv)

        # --- 5. Gemini 深度解析 ---
        st.markdown("---")
        st.subheader("🧠 決策大腦深度解析")
        
        # 動態調整 Prompt
        data_status = "【完全體：含機構數據】" if m['advanced'] else "【降規模式：僅含基礎量價】"
        prompt = f"""
        你是華爾街分析師。當前為 {data_status}。
        目標：{stock_target} | 市場定調：{mode_select}
        量化數據：價格{m['price']}, PEG{m['peg']}, RVOL{m['rvol']}, VCP{m['vcp']}%
        機構數據：{m['advanced']}
        
        若機構數據為空或缺漏，請在報告開頭給予警告，並請求 BOSS 提供「自由現金流」或「法人籌碼」以完善 DD。
        格式：1.可行結論, 2.核心依據, 3.執行步驟, 4.風險。
        繁體中文輸出。
        """
        
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            st.markdown(response.text)
        except Exception as e:
            st.error(f"大腦連線失敗: {e}")