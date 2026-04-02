# 🛡️ WallWin_Gem (華爾街致勝寶石)

**機構級量化決策輔助引擎 (Quantitative Decision Engine powered by Gemini AI)**

WallWin_Gem 是一套專為高階經理人與操盤手打造的 SaaS 級別量化分析系統。結合了即時金融數據擷取、技術指標演算法，以及 Google Gemini 最新世代大型語言模型，提供「數據過濾 ➔ 演算法判定 ➔ AI 深度解析」的端到端（End-to-End）決策支援。

## 🚀 核心戰略架構 (Core Features)

* **雙軌演算法矩陣 (Dual-Track Algorithm):**
    * **白馬股模式 (Value/Growth):** 專注於基本面護城河，運用 P/E (本益比)、PEG (本益成長比)、P/B (股價淨值比) 評估安全邊際與合理估值。
    * **黑馬股模式 (Momentum/Breakout):** 專注於量價籌碼動能，運用 RVOL (相對成交量)、VCP (波動收縮型態)、RSI 捕捉轉機與突破訊號。
* **動態模型雷達 (Dynamic AI Radar):** 內建防禦性 AI 路由機制。自動向 Google 伺服器索取當下可用模型清單，嚴格剔除純語音 (TTS)、舊視覺 (Vision) 與機器人 (Robotics) 測試模型，並強制優先呼叫最新世代的 `Gemini Flash` 模型，具備抗 429 (配額耗盡) 與抗 400 (模態衝突) 的自我降階容錯能力。
* **HITL 人機協同覆蓋 (Human-in-the-loop):** 具備參數微調滑桿與數據覆蓋開關。當外部 API (如 Yahoo Finance) 財報數據缺失或失真時，允許操盤手手動注入真實 PEG 數據，強制 AI 基於校準後的真實數據進行推演。
* **機構級 DD 報告 (Due Diligence Report):** AI 輸出嚴格受控於「繁體中文鐵律」與「四段式格式強制約束 (結論-依據-步驟-風險)」，徹底消滅幻覺與廢話。

## 🛠️ 技術棧 (Tech Stack)

* **前端介面 & 部署:** Streamlit / Streamlit Community Cloud
* **數據與指標處理:** `yfinance`, `pandas`, `ta` (Technical Analysis Library)
* **AI 決策大腦:** `google-generativeai` (Gemini 2.5/2.0 API)

## 🔐 部署與資安紀律 (Deployment & Security)

本專案採 CI/CD 雲端部署架構，嚴格遵守密碼學隔離原則：
1. 核心程式碼 (`app.py`) 與依賴清單 (`requirements.txt`) 託管於 GitHub Private Repository。
2. API Key 絕對禁止硬編碼 (Hardcoding)。本地端依賴 `.streamlit/secrets.toml` 與 `.gitignore` 建立防護罩；雲端則透過 Streamlit Advanced Settings 的 Secrets 模組進行環境變數注入。

---
*Developed & Architected for BOSS (Eric PAN)*
