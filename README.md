# 🛡️ WallWin_Gem (華爾街致勝寶石)

**機構級量化決策輔助引擎 (Deterministic Quantitative Decision Engine)**

WallWin_Gem 是一套專為高階經理人與操盤手打造的量化分析系統。結合金融數據擷取、技術指標演算法與 `wallwin_core` 的 deterministic quant engine，提供「數據輸入 ➔ 規則計算 ➔ 結構化結果／規則式摘要」的決策支援。選配的 AI 文字解讀由使用者將匯出的資料包交給外部台股GPT V2 完成，不參與計算核心。

## 🚀 核心戰略架構 (Core Features)

* **雙軌演算法矩陣 (Dual-Track Algorithm):**
    * **白馬股模式 (Value/Growth):** 專注於基本面護城河，運用 P/E (本益比)、PEG (本益成長比)、P/B (股價淨值比) 評估安全邊際與合理估值。
    * **黑馬股模式 (Momentum/Breakout):** 專注於量價籌碼動能，運用 RVOL (相對成交量)、VCP (波動收縮型態)、RSI 捕捉轉機與突破訊號。
* **確定性量化核心 (Deterministic Quant Engine):** 分數、燈號、回測與風控由明確規則計算。`app.py` 的分析與回測優先呼叫 `wallwin_core`，失敗時回退 V2 規則函式；`api_app.py` 提供同一套 core 的 FastAPI HTTP layer。計算核心不得呼叫 LLM，也不隱性抓取網路資料。
* **HITL 人機協同覆蓋 (Human-in-the-loop):** 具備參數微調滑桿與數據覆蓋開關。當外部 API (如 Yahoo Finance) 財報數據缺失或失真時，允許操盤手手動注入校準資料，由規則引擎依輸入資料計算。
* **規則式報告與選配 AI 解讀:** 系統產生非 AI 摘要及台股GPT JSON／Markdown／PDF 資料包。「AI 投審會決議」頁面提供下載與外部 GPT 連結，使用者須自行上傳或貼上資料包；目前沒有自動 LLM 呼叫。外部台股GPT V2 僅做文字解讀、反方質疑與缺資料整理，不得重算 WallWin 分數或自行補齊缺漏數字。交接規則見 [`TAIGPT_WALLWIN_HANDOFF.md`](TAIGPT_WALLWIN_HANDOFF.md)。

## 🛠️ 技術棧 (Tech Stack)

* **前端介面 & 部署:** Streamlit / Streamlit Community Cloud
* **數據與指標處理:** `yfinance`, `pandas`, `ta` (Technical Analysis Library)
* **量化計算核心:** 本 repository 的 `wallwin_core` Python package，不依賴 LLM
* **圖表與報告:** `plotly`, `reportlab`
* **HTTP API:** `fastapi`, `uvicorn`；現行 `requirements.txt` 另列 `httpx2`

依賴以 [`requirements.txt`](requirements.txt) 為準；目前沒有 `google-generativeai` 或 `google-genai`。執行量化分析與規則式報告不需要 Gemini API Key；外部台股GPT 解讀不屬於本程式的 Python 依賴。

## 🔐 部署與資安紀律 (Deployment & Security)

本 repository 目前為 GitHub Public Repository；公開原始碼與部署環境的秘密設定須分開管理：

1. `app.py`、`api_app.py`、`wallwin_core/` 與 `requirements.txt` 均在本公開 repository。
2. 密碼、API Key 與敏感資料禁止硬編碼或提交。`app.py` 目前從 Streamlit Secrets 讀取 `APP_PASSWORD`；本地可使用被 `.gitignore` 排除的 `.streamlit/secrets.toml`，雲端使用 Streamlit 的 Secrets 設定。量化核心不直接讀取 secrets。詳見 [`SECURITY.md`](SECURITY.md)。

---
*Developed & Architected for BOSS (Eric PAN)*
