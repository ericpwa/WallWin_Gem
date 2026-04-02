import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import google.generativeai as genai

# --- 1. 核心運算引擎 (雙軌 HITL 支援) ---
def calculate_quant_matrix(ticker_obj, df, advanced_df, rvol_threshold, vcp_threshold):
    info = ticker_obj.info
    m = {
        "price": df['Close'].iloc[-1],
        "volume": df['Volume'].iloc[-1],
        "pe": info.get('trailingPE', 0.0),
        "pb": info.get('priceToBook', 0.0),
        "beta": info.get('beta', 1.0),
        "peg": (info.get('trailingPE', 0.0) / (info.get('earningsQuarterlyGrowth', 0) * 100)) if info.get('earningsQuarterlyGrowth', 0) > 0 else 999.0,
        "rvol": df['Volume'].iloc[-1] / df['Volume'].rolling(window=20).mean().iloc[-1] if not df['Volume'].rolling(window=20).mean().empty else 0,
        "vcp": (df['High'].tail(5).max() - df['Low'].tail(5).min()) / df['Low'].tail(5).min() * 100,
        "vwap": ta.volume.VolumeWeightedAveragePrice(high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume']).volume_weighted_average_price().iloc[-1],
        "atr_pct": (ta.volatility.AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close']).average_true_range().iloc[-1] / df['Close'].iloc[-1]) * 100
    }
    
    # [無限擴充架構] 動態吸收 CSV 機構級數據
    m["advanced"] = {}
    if advanced_df is not None:
        try:
            row_dict = advanced_df[advanced_df['股號'] == stock_target].iloc[0].to_dict()
            row_dict.pop('股號', None)
            m["advanced"] = {str(k): v for k, v in row_dict.items() if pd.notna(v)}
        except Exception:
            st.sidebar.error("❌ CSV 股號不匹配或格式有誤")
            
    return m

# --- 2. 戰術燈號 ---
def get_traffic_light(m, mode, strategy, r_thresh, v_thresh):
    if mode == "白馬股 (價值/已驗證)":
        if strategy == "穩健型 (合理成長)":
            if m['peg'] < 0.75: return "🟢 綠燈", "低估成長，逢低進場佈局"
            elif m['peg'] > 1.2: return "🔴 紅燈", "估值過熱，留意獲利了結"
            else: return "🔵 藍燈", "估值合理，穩定續抱"
        else:
            if m['pb'] < 1.5: return "🟢 綠燈", "淨值保護，安全進場"
            else: return "🔵 藍燈", "股價平穩，持續觀察"
    else: 
        if m['rvol'] > r_thresh and m['vcp'] < v_thresh: return "🟢 綠燈", "爆量突破，積極跟進動能"
        else: return "🔵 藍燈", "量縮震盪，等待表態"

# --- 3. 頁面初始化 ---
st.set_page_config(page_title="WallWin Gem 量化系統", layout="wide")
st.title("🛡️ WallWin Gem 戰略指揮中心 (大統一完全體)")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.error("❌ 缺失 API Key"); st.stop()

# --- 4. 側邊欄：戰略控制台 (整合雙軌 HITL) ---
st.sidebar.header("⚙️ 戰略控制台")
stock_target = st.sidebar.text_input("🎯 目標股號", "2206.TW")
mode_select = st.sidebar.radio("市場定調", ["白馬股 (價值/已驗證)", "黑馬潛力股 (轉機/突破)"])
strategy_select = st.sidebar.selectbox("戰略模組", ["穩健型 (合理成長)", "保守型 (防禦/股息)", "積極型 (動能/短線)"])

st.sidebar.markdown("---")
st.sidebar.subheader("🎚️ 戰略敏感度微調")
r_thresh = st.sidebar.slider("RVOL 爆量閾值", 1.0, 5.0, 2.0, 0.1)
v_thresh = st.sidebar.slider("VCP 壓縮限度 (%)", 1.0, 10.0, 5.0, 0.5)

# [HITL 軌道 1] 手動覆蓋 PEG
st.sidebar.markdown("---")
st.sidebar.subheader("🛠️ HITL 基礎人工校準")
manual_override = st.sidebar.toggle("啟用 PEG 數據覆蓋")
hitl_peg = 999.0
if manual_override:
    hitl_peg = st.sidebar.number_input("手動修正 PEG 數據", 0.0, 10.0, 1.2, 0.1)

# [HITL 軌道 2] 擴充 CSV 上傳
st.sidebar.markdown("---")
st.sidebar.subheader("📁 HITL 進階私房數據 (CSV)")
uploaded_file = st.sidebar.file_uploader("上傳 .csv 檔案 (解鎖進階分析)", type="csv")
advanced_data = None
if uploaded_file:
    advanced_data = pd.read_csv(uploaded_file)
    st.sidebar.success("✅ 私房數據已掛載，大腦權限解鎖！")
else:
    st.sidebar.warning("⚠️ 降規模式：未掛載 CSV 數據")

analyze_button = st.sidebar.button("🚀 啟動深度量化解析", use_container_width=True)

# --- 5. 運算與 UI 展示 ---
if analyze_button:
    with st.spinner(f"擷取 {stock_target} 數據中..."):
        ticker = yf.Ticker(stock_target)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 20: st.error("❌ 查無資料或標的已下市"); st.stop()
        
        m = calculate_quant_matrix(ticker, hist, advanced_data, r_thresh, v_thresh)
        
        # 執行 PEG 覆蓋邏輯
        if manual_override:
            m['peg'] = hitl_peg
            st.warning(f"🛠️ HITL 介入：已手動將 PEG 覆蓋為 {hitl_peg}")
            
        st.info(f"**今日現價：`{m['price']:.2f}`** │ 成交量：`{m['volume']/1000:,.0f}` 張")
        
        col1, col2 = st.columns([2, 1])
        with col1: st.line_chart(hist['Close'].tail(120)) 
        with col2:
            st.subheader("核心量化指標")
            st.metric("P/E", f"{m['pe']:.2f}")
            st.metric("PEG", f"{m['peg']:.2f}", delta="手動覆蓋" if manual_override else ("數據缺失" if m['peg'] == 999 else None))
            st.metric("RVOL", f"{m['rvol']:.2f}x")
            st.metric("VCP", f"{m['vcp']:.2f}%")
            
            if m['advanced']:
                st.markdown("---")
                st.markdown("**💎 成功匯入之機構數據：**")
                for k, v in m['advanced'].items(): st.write(f"- {k}: **{v}**")

            st.markdown("---")
            light_color, advice = get_traffic_light(m, mode_select, strategy_select, r_thresh, v_thresh)
            st.subheader("🚦 戰術判定燈號")
            st.write(f"**{light_color}**：{advice}")

        # --- 6. Gemini 深度解析 ---
        st.markdown("---")
        st.subheader("🧠 決策大腦深度解析 (Gemini AI)")
        
        data_status = "【完全體：已融合 BOSS 上傳之 CSV 機構數據】" if m['advanced'] else "【降規模式：缺乏高階基本面數據，請提醒 BOSS 上傳】"
        prompt = f"""
        你是一位華爾街頂級量化分析師 (DD 模式)。狀態：{data_status}。
        目標：{stock_target} | 市場定調：{mode_select} | 戰略模組：{strategy_select}
        燈號：{light_color} - {advice}
        量化基準數據：股價 {m['price']:.2f}, P/E {m['pe']:.2f}, PEG {m['peg']:.2f}, RVOL {m['rvol']:.2f}, VCP {m['vcp']:.2f}%, VWAP {m['vwap']:.2f}, ATR {m['atr_pct']:.2f}%
        BOSS CSV 私房數據：{m['advanced']}
        
        絕對約束：
        1. 【語言鐵律】：必須全篇使用「繁體中文 (Traditional Chinese)」，嚴禁簡體字。
        2. 【格式鐵律】：嚴格依照「1.可行結論、2.核心依據、3.執行步驟、4.風險與替代方案」四段結構。
        """
        
        try:
            available_models = [md.name for md in genai.list_models() if 'generateContent' in md.supported_generation_methods and 'gemini' in md.name.lower() and 'vision' not in md.name.lower() and 'robotics' not in md.name.lower() and 'tts' not in md.name.lower()]
            target_models = sorted([md for md in available_models if '1.5' in md or '2.0' in md or '2.5' in md], key=lambda x: (0 if 'flash' in x.lower() else 1))[:3]
            
            success = False
            error_logs = []
            
            for model_name in target_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt, stream=True)
                    res_box = st.empty()
                    full_report = ""
                    
                    for chunk in response:
                        if chunk.parts: # 🚨 神經質保全防護網：過濾空包裹
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
                    for err in error_logs: st.info(err)
                    
        except Exception as e: st.error(f"❌ 系統連線基礎異常: {e}")