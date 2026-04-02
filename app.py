import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import numpy as np
import google.generativeai as genai

# --- 1. 核心運算引擎 ---
def calculate_quant_matrix(ticker_obj, df, rvol_threshold, vcp_threshold):
    info = ticker_obj.info
    beta = info.get('beta', 1.0)
    pb_ratio = info.get('priceToBook', 0.0)
    current_pe = info.get('trailingPE', 0.0)
    eps_growth = (info.get('earningsQuarterlyGrowth', 0.0) or 0) * 100 
    peg = current_pe / eps_growth if eps_growth > 0 else 999.0
    
    df['Vol_20MA'] = df['Volume'].rolling(window=20).mean()
    rvol = df['Volume'].iloc[-1] / df['Vol_20MA'].iloc[-1] if not df['Vol_20MA'].empty else 0
    recent_df = df.tail(5)
    vcp_range = (recent_df['High'].max() - recent_df['Low'].min()) / recent_df['Low'].min() * 100
    ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
    is_above_ma20 = df['Close'].iloc[-1] > ma20
    rsi = ta.momentum.RSIIndicator(df['Close']).rsi().iloc[-1]

    return {
        "white_horse": {"beta": beta, "pb": pb_ratio, "peg": peg, "pe": current_pe},
        "dark_horse": {"rvol": rvol, "vcp": vcp_range, "above_ma20": is_above_ma20, "rsi": rsi},
        "price": df['Close'].iloc[-1]
    }

# --- 2. 戰術燈號 ---
def get_traffic_light(m, mode, strategy, r_thresh, v_thresh):
    if mode == "白馬股 (價值/已驗證)":
        if strategy == "穩健型 (合理成長)":
            if m['white_horse']['peg'] < 0.75: return "🟢 綠燈", "低估成長，逢低進場佈局"
            elif m['white_horse']['peg'] > 1.2: return "🔴 紅燈", "估值過熱，留意獲利了結"
            else: return "🔵 藍燈", "估值合理，穩定續抱"
        else: # 保守型
            if m['white_horse']['pb'] < 1.5: return "🟢 綠燈", "淨值保護，安全進場"
            else: return "🔵 藍燈", "股價平穩，持續觀察"
    else: # 黑馬潛力股
        if m['dark_horse']['rvol'] > r_thresh and m['dark_horse']['vcp'] < v_thresh and m['dark_horse']['above_ma20']:
            return "🟢 綠燈", "爆量突破，積極跟進動能"
        elif m['dark_horse']['rsi'] > 80:
            return "🔴 紅燈", "動能極度過熱，逢高賣出"
        else:
            return "🔵 藍燈", "量縮震盪，等待表態"

# --- 3. 頁面初始化 ---
st.set_page_config(page_title="WallWin Gem 量化系統", layout="wide")
st.title("🛡️ WallWin Gem 戰略指揮中心")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except Exception:
    st.error("❌ 資安警告：未偵測到 API Key")
    st.stop()

# --- 4. 側邊欄：戰略控制台 ---
st.sidebar.header("⚙️ 戰略控制台")
stock_target = st.sidebar.text_input("🎯 目標股號", "2317.TW")
mode_select = st.sidebar.radio("市場定調", ["白馬股 (價值/已驗證)", "黑馬潛力股 (轉機/突破)"])
strategy_select = st.sidebar.selectbox("戰略模組", ["穩健型 (合理成長)", "保守型 (防禦/股息)", "積極型 (動能/短線)"])

st.sidebar.markdown("---")
st.sidebar.subheader("🎚️ 戰略敏感度微調")
r_thresh = st.sidebar.slider("RVOL 爆量閾值", 1.0, 5.0, 2.0, 0.1)
v_thresh = st.sidebar.slider("VCP 壓縮限度 (%)", 1.0, 10.0, 5.0, 0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("🛠️ HITL 數據人工校準")
manual_override = st.sidebar.toggle("啟用數據覆蓋")
hitl_peg = 999.0
if manual_override:
    hitl_peg = st.sidebar.number_input("手動修正 PEG 數據", 0.0, 10.0, 1.0, 0.1)

analyze_button = st.sidebar.button("🚀 啟動深度量化解析", use_container_width=True)

# --- 5. 主畫面數據展示與 AI 生成 ---
if analyze_button:
    with st.spinner(f"正在擷取 {stock_target} 數據並喚醒 Gemini ..."):
        ticker = yf.Ticker(stock_target)
        hist = ticker.history(period="1y")
        
        if hist.empty or len(hist) < 2:
            st.error("⚠️ 數據毒性警告：無法獲取足夠歷史資料。")
            st.stop()
            
        m = calculate_quant_matrix(ticker, hist, r_thresh, v_thresh)
        
        if manual_override:
            m['white_horse']['peg'] = hitl_peg
            st.warning(f"🛠️ HITL 介入：已手動將 PEG 覆蓋為 {hitl_peg}")

        today_s, yest_s = hist.iloc[-1], hist.iloc[-2]
        st.info(f"**今日現價：`{today_s['Close']:.2f}`** │ 昨日收盤：`{yest_s['Close']:.2f}` │ 成交量：`{yest_s['Volume']/1000:,.0f}` 張")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.line_chart(hist['Close'].tail(120)) 
        with col2:
            st.subheader("核心量化指標")
            if mode_select == "白馬股 (價值/已驗證)":
                st.metric("P/E", f"{m['white_horse']['pe']:.2f}")
                st.metric("PEG", f"{m['white_horse']['peg']:.2f}", delta="數據缺失" if m['white_horse']['peg'] == 999 else None)
            else:
                st.metric("RVOL", f"{m['dark_horse']['rvol']:.2f}x")
                st.metric("VCP", f"{m['dark_horse']['vcp']:.2f}%")
            
            st.markdown("---")
            light_color, advice = get_traffic_light(m, mode_select, strategy_select, r_thresh, v_thresh)
            st.subheader("🚦 戰術判定燈號")
            if "綠燈" in light_color: st.success(f"**{light_color}**：{advice}")
            elif "紅燈" in light_color: st.error(f"**{light_color}**：{advice}")
            else: st.info(f"**{light_color}**：{advice}")

        # --- 6. 大腦連線與終極容錯雷達 ---
        st.markdown("---")
        st.subheader("🧠 決策大腦深度解析 (Gemini AI)")
        
        prompt = f"""
        你是一位華爾街頂級量化分析師 (嚴格執行 DD 模式)。
        分析目標：{stock_target}
        市場定調：{mode_select}
        戰略模組：{strategy_select}
        當前燈號：{light_color} - {advice}
        數據：股價 {today_s['Close']:.2f}, P/E {m['white_horse']['pe']:.2f}, PEG {m['white_horse']['peg']:.2f}, RVOL {m['dark_horse']['rvol']:.2f}, VCP {m['dark_horse']['vcp']:.2f}%
        
        絕對約束：
        1. 【語言鐵律】：必須全篇使用「繁體中文 (Traditional Chinese)」輸出，嚴禁簡體字。
        2. 【格式鐵律】：嚴格依照「1.可行結論、2.核心依據、3.執行步驟、4.風險與替代方案」四段結構。
        """
        
        try:
            # 嚴格封殺 tts/vision/robotics，只留純淨文本模型
            available_models = [
                m.name for m in genai.list_models() 
                if 'generateContent' in m.supported_generation_methods 
                and 'gemini' in m.name.lower() 
                and 'vision' not in m.name.lower() 
                and 'robotics' not in m.name.lower()
                and 'tts' not in m.name.lower()
            ]
            
            # 強制將速度快、免費額度極高的 flash 模型排在第一順位，避開 pro 的 429 限制
            target_models = sorted(
                [m for m in available_models if '1.5' in m or '2.0' in m or '2.5' in m],
                key=lambda x: (0 if 'flash' in x.lower() else 1)
            )[:3]
            
            if not target_models:
                st.error("❌ 雷達失效：找不到任何可用模型。")
                st.stop()
                
            st.caption(f"📡 雷達精準鎖定模型：`{target_models}`")

            success = False
            error_logs = []
            
            for model_name in target_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(prompt, stream=True)
                    res_box = st.empty()
                    full_report = ""
                    for chunk in response:
                        full_report += chunk.text
                        res_box.markdown(full_report + "▌")
                    res_box.markdown(full_report)
                    success = True
                    st.success(f"✅ 成功透過 **{model_name}** 完成深度解析。")
                    break
                except Exception as e:
                    error_logs.append(f"⚠️ **{model_name}** 拒絕連線：`{e}`")
                    continue
            
            if not success: 
                st.error("❌ 所有 AI 模型皆無法生成報告。錯誤明細如下 (如為 429 請等待幾分鐘讓額度重置)：")
                for err in error_logs:
                    st.warning(err)
                    
        except Exception as e: 
            st.error(f"❌ 系統連線基礎異常: {e}")