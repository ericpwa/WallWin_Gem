from html import escape
from io import BytesIO

import pandas as pd
import streamlit as st
import yfinance as yf
import ta
from google import genai

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except Exception:
    go = None
    make_subplots = None

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


WALLWIN_GLOSSARY = [
    {
        "category": "WallWin 核心",
        "term": "多因子矩陣",
        "formula": "總分 = Σ(因子分數 × 權重)",
        "explain": "把估值、成長、品質、動能、低波動、流動性與風控轉成同一套 0-100 分矩陣，讓不同股票能被同一把尺比較。",
        "example": "白馬投資模式會提高 Quality、Value、Risk 權重；黑馬波段模式會提高 Momentum、Liquidity 權重。",
    },
    {
        "category": "WallWin 核心",
        "term": "白馬模式",
        "formula": "偏重 Value + Quality + Dividend Safety + Risk Control",
        "explain": "用來評估成熟、穩健、具長期價值或配息能力的股票。",
        "example": "ROE 穩定、負債低、FCF 充足且估值合理，白馬分通常較高。",
    },
    {
        "category": "WallWin 核心",
        "term": "黑馬模式",
        "formula": "偏重 Momentum + Growth + Liquidity + Breakout Quality",
        "explain": "用來評估轉機、突破、題材發酵與短中期價格動能較強的股票。",
        "example": "股價接近 52 週高點、RVOL 放大、VCP 收斂後突破，黑馬分通常較高。",
    },
    {
        "category": "WallWin 核心",
        "term": "HITL 人機協同",
        "formula": "校準後分數 = 系統分數 + 催化加分 - 風險扣分",
        "explain": "Human-in-the-loop，讓使用者把系統拿不到的私房資料或基本面判斷納入校準。",
        "example": "若公司即將法說且有新訂單，可加催化分；若有訴訟或籌碼風險，可加風險扣分。",
    },
    {
        "category": "交易週期",
        "term": "波段",
        "formula": "通常持有數日到數週，重視趨勢、突破與風險報酬比",
        "explain": "目標是吃一段價格趨勢，而不是只看單日波動或長期股利。",
        "example": "突破整理區後，以固定停損、停利與移動停損管理部位。",
    },
    {
        "category": "交易週期",
        "term": "投資",
        "formula": "通常持有數月到多年，重視企業品質、估值、現金流與股利安全",
        "explain": "把股票視為企業所有權的一部分，追求長期資本利得與現金分配。",
        "example": "ROIC 高、FCF 穩定且估值低於歷史分位時，更符合長期投資條件。",
    },
    {
        "category": "交易週期",
        "term": "當沖",
        "formula": "同日進出，重視即時流動性、VWAP、分時量能與滑價",
        "explain": "不隔夜持倉，對成本、滑價、成交量與停損紀律非常敏感。",
        "example": "5 分 K 站上 VWAP、RVOL 放大且買盤延續，才比較適合做多當沖。",
    },
    {
        "category": "基本面品質",
        "term": "ROE 股東權益報酬率",
        "formula": "ROE = 淨利 / 股東權益 × 100%",
        "explain": "衡量公司用股東資本賺錢的能力。",
        "example": "ROE 20% 代表每 100 元股東權益約創造 20 元獲利，但仍要搭配負債一起看。",
    },
    {
        "category": "基本面品質",
        "term": "ROA 資產報酬率",
        "formula": "ROA = 淨利 / 總資產 × 100%",
        "explain": "衡量公司運用全部資產創造獲利的效率。",
        "example": "重資產產業 ROA 通常較低，應和同業比較。",
    },
    {
        "category": "基本面品質",
        "term": "ROIC 投入資本報酬率",
        "formula": "ROIC = 稅後營業利益 / 投入資本 × 100%",
        "explain": "衡量公司把營運資本投入後產生報酬的能力，常用來觀察護城河。",
        "example": "ROIC 長期高於資金成本，代表公司較可能創造經濟利潤。",
    },
    {
        "category": "基本面品質",
        "term": "毛利率",
        "formula": "毛利率 = 毛利 / 營收 × 100%",
        "explain": "反映產品或服務扣除直接成本後的獲利空間。",
        "example": "毛利率上升可能代表產品組合改善、漲價能力提升或成本下降。",
    },
    {
        "category": "基本面品質",
        "term": "營益率",
        "formula": "營益率 = 營業利益 / 營收 × 100%",
        "explain": "衡量本業扣除營運費用後的獲利能力。",
        "example": "營收成長但營益率下降，可能表示費用擴張或價格競爭加劇。",
    },
    {
        "category": "基本面品質",
        "term": "淨利率",
        "formula": "淨利率 = 淨利 / 營收 × 100%",
        "explain": "衡量公司最後留下多少稅後盈餘。",
        "example": "高淨利率通常代表品牌、技術、規模或成本控管具優勢。",
    },
    {
        "category": "財務安全",
        "term": "Debt/Equity 負債權益比",
        "formula": "Debt/Equity = 總負債 / 股東權益",
        "explain": "衡量公司槓桿程度，越高代表財務風險通常越高。",
        "example": "景氣循環股若 Debt/Equity 太高，遇到景氣下行時風險會放大。",
    },
    {
        "category": "財務安全",
        "term": "Current Ratio 流動比率",
        "formula": "Current Ratio = 流動資產 / 流動負債",
        "explain": "衡量短期償債能力。",
        "example": "流動比率低於 1 代表短期負債可能高於短期可用資產。",
    },
    {
        "category": "財務安全",
        "term": "Interest Coverage 利息保障倍數",
        "formula": "Interest Coverage = EBIT / 利息費用",
        "explain": "衡量營業利益能覆蓋利息支出的倍數。",
        "example": "倍數越高，公司支付利息的壓力通常越低。",
    },
    {
        "category": "現金流",
        "term": "Operating Cash Flow 營業現金流",
        "formula": "OCF = 本業營運產生的現金流入 - 流出",
        "explain": "比盈餘更接近實際收進來的本業現金。",
        "example": "淨利成長但 OCF 長期偏弱，可能代表應收帳款或存貨壓力。",
    },
    {
        "category": "現金流",
        "term": "Free Cash Flow 自由現金流",
        "formula": "FCF = 營業現金流 - 資本支出",
        "explain": "公司維持營運與投資後可自由分配的現金。",
        "example": "FCF 穩定的公司較有能力配息、買回庫藏股或還債。",
    },
    {
        "category": "現金流",
        "term": "FCF Yield 自由現金流殖利率",
        "formula": "FCF Yield = 自由現金流 / 市值 × 100%",
        "explain": "用現金流角度衡量估值吸引力。",
        "example": "FCF Yield 高於同業且現金流穩定，可能代表估值較有安全邊際。",
    },
    {
        "category": "估值",
        "term": "P/E 本益比",
        "formula": "P/E = 股價 / 每股盈餘 EPS",
        "explain": "市場願意為每 1 元盈餘支付多少價格。",
        "example": "P/E 15 倍代表投資人為 1 元 EPS 支付 15 元股價。",
    },
    {
        "category": "估值",
        "term": "PEG 本益成長比",
        "formula": "PEG = P/E / 盈餘成長率",
        "explain": "把本益比和成長率放在一起看，避免只看便宜或只看成長。",
        "example": "P/E 30、成長率 30% 時 PEG 約 1；若成長率只有 10%，PEG 約 3。",
    },
    {
        "category": "估值",
        "term": "P/B 股價淨值比",
        "formula": "P/B = 股價 / 每股淨值",
        "explain": "市場價格相對帳面淨資產的倍數。",
        "example": "金融、資產型公司常用 P/B 和 ROE 一起判斷估值合理性。",
    },
    {
        "category": "估值",
        "term": "P/S 股價營收比",
        "formula": "P/S = 市值 / 營收",
        "explain": "用營收衡量市場估值，常用於獲利尚不穩定的成長股。",
        "example": "P/S 高但毛利率與成長率下降，估值風險會提高。",
    },
    {
        "category": "估值",
        "term": "EV/EBITDA",
        "formula": "EV/EBITDA = 企業價值 / EBITDA",
        "explain": "用企業價值相對營運現金獲利能力衡量估值，較能納入負債影響。",
        "example": "同業比較時，EV/EBITDA 較低且成長品質相近，估值通常較有吸引力。",
    },
    {
        "category": "估值",
        "term": "估值分位 P/E percentile / P/B percentile",
        "formula": "分位 = 目前估值位於歷史估值序列的位置",
        "explain": "判斷目前估值相對自身歷史是偏高、偏低或中性。",
        "example": "P/E 位於歷史 20 分位，代表目前比過去多數時間便宜。",
    },
    {
        "category": "成長與修正",
        "term": "YoY 年增率",
        "formula": "YoY = 本期數值 / 去年同期數值 - 1",
        "explain": "用來消除季節性，觀察和去年同期相比是否成長。",
        "example": "營收 YoY +25% 代表本月營收比去年同月增加 25%。",
    },
    {
        "category": "成長與修正",
        "term": "QoQ 季增率",
        "formula": "QoQ = 本季數值 / 上季數值 - 1",
        "explain": "觀察短期成長動能是否加速或降溫。",
        "example": "EPS QoQ 連續轉強，可能表示景氣或產品週期改善。",
    },
    {
        "category": "成長與修正",
        "term": "Earnings Revision 盈餘修正",
        "formula": "修正方向 = 分析師上修次數 - 下修次數",
        "explain": "衡量市場對未來盈餘預期是轉好還是轉差。",
        "example": "若法說後多家券商上修 EPS，通常有利評價與動能。",
    },
    {
        "category": "股利",
        "term": "Dividend Yield 殖利率",
        "formula": "殖利率 = 每股股利 / 股價 × 100%",
        "explain": "衡量用目前股價買進可取得的股利報酬率。",
        "example": "殖利率 5% 代表以目前價格買進，股利約占成本 5%。",
    },
    {
        "category": "股利",
        "term": "Payout Ratio 配息率",
        "formula": "配息率 = 現金股利 / EPS × 100%",
        "explain": "衡量盈餘中有多少比例拿來配息。",
        "example": "配息率長期超過 100%，若沒有特殊原因，股利可持續性較弱。",
    },
    {
        "category": "股利",
        "term": "Dividend Safety 股利安全性",
        "formula": "股利安全 = 殖利率合理性 + 配息率 + FCF 覆蓋率",
        "explain": "判斷股利是否有足夠盈餘與現金流支撐。",
        "example": "高殖利率但 FCF 不足，可能是陷阱殖利率。",
    },
    {
        "category": "技術動能",
        "term": "RVOL 相對成交量",
        "formula": "RVOL = 今日成交量 / 近期平均成交量",
        "explain": "衡量今天成交量相對平常是否明顯放大。",
        "example": "RVOL 2.0x 代表成交量約為近期平均的 2 倍，突破可信度通常較高。",
    },
    {
        "category": "技術動能",
        "term": "VCP 波動收縮型態",
        "formula": "VCP 可用近期期幅或 ATR 收縮程度近似",
        "explain": "價格波動逐步收斂，代表籌碼可能沉澱，等待突破方向。",
        "example": "整理時高低點越縮越窄，最後放量突破，是典型黑馬訊號之一。",
    },
    {
        "category": "技術動能",
        "term": "RSI 相對強弱指標",
        "formula": "RSI = 100 - 100 / (1 + 平均漲幅 / 平均跌幅)",
        "explain": "衡量近期漲跌力道，常用 0-100 判斷動能與過熱。",
        "example": "RSI 50-70 常代表偏強；超過 80 可能過熱，需看趨勢與量能確認。",
    },
    {
        "category": "技術動能",
        "term": "Relative Strength 相對強弱",
        "formula": "相對強弱 = 個股報酬率 - 大盤報酬率",
        "explain": "觀察個股是否跑贏基準指數。",
        "example": "大盤跌 3%，個股漲 2%，代表相對強弱為 +5%。",
    },
    {
        "category": "趨勢品質",
        "term": "MA 均線與 MA slope",
        "formula": "MA = N 日收盤均價；MA slope = MA 現值 / MA 過去值 - 1",
        "explain": "均線看趨勢位置，斜率看趨勢方向與速度。",
        "example": "股價在 MA20/MA50 上方且 MA50 slope 為正，趨勢品質較好。",
    },
    {
        "category": "趨勢品質",
        "term": "Higher High / Higher Low",
        "formula": "新高高於前高，回檔低點高於前低",
        "explain": "上升趨勢的價格結構。",
        "example": "突破後回測不破前低，再創新高，代表多方結構延續。",
    },
    {
        "category": "趨勢品質",
        "term": "52 週高點距離",
        "formula": "距離 = 現價 / 52週高點 - 1",
        "explain": "衡量股價距離一年高點多遠，常用來判斷強勢程度。",
        "example": "距離 52 週高點 -3% 通常比 -35% 更接近強勢股條件。",
    },
    {
        "category": "趨勢品質",
        "term": "ADX 趨勢強度",
        "formula": "ADX 由 +DI、-DI 推導，衡量趨勢強弱",
        "explain": "ADX 越高代表趨勢越明顯，但不判斷多空方向。",
        "example": "ADX 高於 25 常被視為趨勢較明確。",
    },
    {
        "category": "風險波動",
        "term": "ATR 平均真實波幅",
        "formula": "ATR = True Range 的 N 日平均",
        "explain": "衡量價格平均波動幅度，常用於停損距離與部位控管。",
        "example": "ATR% 越高，代表股價日常波動越大，停損需更嚴格或部位要縮小。",
    },
    {
        "category": "風險波動",
        "term": "布林帶寬度",
        "formula": "寬度 = (上軌 - 下軌) / 收盤價 × 100%",
        "explain": "衡量價格波動收縮或擴張。",
        "example": "布林帶寬度處於低分位後放量突破，常被視為波動擴張訊號。",
    },
    {
        "category": "風險波動",
        "term": "Gap Risk 跳空風險",
        "formula": "Gap = 今日開盤 / 昨日收盤 - 1",
        "explain": "衡量開盤跳空造成停損失效或滑價擴大的風險。",
        "example": "財報或重大消息後跳空，實際成交價可能遠離原停損價。",
    },
    {
        "category": "量價交易",
        "term": "VWAP 成交量加權平均價",
        "formula": "VWAP = Σ(成交價 × 成交量) / Σ成交量",
        "explain": "衡量當日市場平均成交成本，常用於當沖方向判斷。",
        "example": "價格站上 VWAP 且量能延續，短線多方較有優勢。",
    },
    {
        "category": "量價交易",
        "term": "突破量比",
        "formula": "突破量比 = 突破日成交量 / 近期平均成交量",
        "explain": "衡量突破是否有成交量支持。",
        "example": "突破前高但量比低於 1，可能是假突破風險較高。",
    },
    {
        "category": "量價交易",
        "term": "爆量長上影否決",
        "formula": "上影線比例 = (最高價 - 收盤價) / 收盤價 × 100%",
        "explain": "放大量卻留下長上影線，可能代表追價買盤被賣壓壓回。",
        "example": "突破當日 RVOL 很高但收盤跌回區間，系統會提高失敗警示。",
    },
    {
        "category": "交易計畫",
        "term": "停損",
        "formula": "停損價 = 進場價 × (1 - 停損%)",
        "explain": "事先定義最大可接受虧損，避免單筆交易失控。",
        "example": "100 元進場、停損 8%，停損價約 92 元。",
    },
    {
        "category": "交易計畫",
        "term": "停利",
        "formula": "停利價 = 進場價 × (1 + 停利%)",
        "explain": "事先定義獲利目標，讓風險報酬比可被評估。",
        "example": "100 元進場、目標 16%，停利價約 116 元。",
    },
    {
        "category": "交易計畫",
        "term": "移動停損",
        "formula": "移動停損價 = 進場後最高價 × (1 - 移動停損%)",
        "explain": "隨價格創高上移停損，保護已出現的未實現獲利。",
        "example": "最高漲到 120 元、移動停損 10%，回落到 108 元附近就出場。",
    },
    {
        "category": "交易成本",
        "term": "交易成本",
        "formula": "淨報酬 = 毛報酬 - 買進成本 - 賣出成本",
        "explain": "包含手續費、稅費等，會直接降低實際績效。",
        "example": "當沖或高週轉策略若成本偏高，勝率再高也可能被成本吃掉。",
    },
    {
        "category": "交易成本",
        "term": "滑價",
        "formula": "滑價 = 預期成交價與實際成交價的差異",
        "explain": "流動性不足或價格快速變動時，實際成交常比預期差。",
        "example": "想用 100 元買進，但成交在 100.2 元，0.2% 就是買進端滑價。",
    },
    {
        "category": "回測",
        "term": "勝率",
        "formula": "勝率 = 獲利交易次數 / 總交易次數 × 100%",
        "explain": "衡量交易中有多少比例賺錢，但不能單獨代表策略好壞。",
        "example": "勝率 40% 但平均賺 10%、平均賠 3%，策略仍可能有正期望值。",
    },
    {
        "category": "回測",
        "term": "獲利因子",
        "formula": "獲利因子 = 總獲利 / 絕對總虧損",
        "explain": "衡量每承擔 1 元虧損能換回多少獲利。",
        "example": "獲利因子 1.8 代表每虧 1 元，總體約賺 1.8 元。",
    },
    {
        "category": "回測",
        "term": "最大回撤",
        "formula": "最大回撤 = 權益曲線高點到後續低點的最大跌幅",
        "explain": "衡量策略最痛的一段資金下滑。",
        "example": "年化報酬高但最大回撤也很大，實際執行時可能難以承受。",
    },
    {
        "category": "回測",
        "term": "Walk-forward 校準",
        "formula": "訓練期選參數/權重 → 下一段測試期驗證 → 向前滾動",
        "explain": "避免只用同一段歷史資料最佳化，降低過度擬合風險。",
        "example": "用 2021 年訓練挑最佳輪廓，再用 2022 上半年測試，接著往後滾動。",
    },
    {
        "category": "回測",
        "term": "Train / Test 訓練窗與測試窗",
        "formula": "訓練窗 = 選參數資料；測試窗 = 驗證資料",
        "explain": "訓練窗用來挑選權重輪廓，測試窗用來觀察下一段真實表現。",
        "example": "訓練 252 日、測試 126 日，約等於用一年資料校準、用半年資料驗證。",
    },
    {
        "category": "風控",
        "term": "否決條件 Hard Flags",
        "formula": "若重大風險成立，分數再高也要降級或暫停",
        "explain": "用來阻止高分但風險不可接受的標的進入交易計畫。",
        "example": "流動性不足、跌破 VWAP、爆量長上影、ATR 過高都可能成為否決警示。",
    },
]


def safe_float(val, default=0.0):
    try:
        if val is None or pd.isna(val) or str(val).strip() == "":
            return default
        return float(val)
    except Exception:
        return default


def normalize_symbol(raw_symbol):
    symbol_text = str(raw_symbol or "").strip().upper()
    if symbol_text.isdigit():
        return f"{symbol_text}.TW"
    return symbol_text


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


def fmt_num(value, digits=2, suffix=""):
    value = safe_float(value, None)
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}{suffix}"


def fmt_big_number(value):
    value = safe_float(value, None)
    if value is None:
        return "N/A"
    abs_value = abs(value)
    if abs_value >= 100_000_000_000:
        return f"{value / 100_000_000_000:.2f} 千億"
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:.2f} 億"
    if abs_value >= 10_000:
        return f"{value / 10_000:.2f} 萬"
    return f"{value:,.0f}"


def pct_label(value):
    value = safe_float(value, None)
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def interpret_score(score):
    if score >= 80:
        return "強勢優勢"
    if score >= 65:
        return "條件成熟"
    if score >= 50:
        return "中性觀察"
    return "偏弱待確認"


def interpret_relative(value, unit="分"):
    value = safe_float(value)
    if value > 8:
        return f"高於基準 {value:.1f}{unit}"
    if value < -8:
        return f"低於基準 {abs(value):.1f}{unit}"
    return f"接近基準 {value:+.1f}{unit}"


def score_reason(score, good_text, weak_text):
    score = safe_float(score)
    if score >= 80:
        return f"{good_text}，屬高分區。"
    if score >= 65:
        return f"{good_text}，條件成熟但仍需搭配風控。"
    if score >= 50:
        return "位於中性區，需等待更多確認訊號。"
    return f"{weak_text}，目前拖累整體評分。"


def score_bar(score):
    score = clamp(safe_float(score))
    if score >= 75:
        color = "#0f9f6e"
    elif score >= 55:
        color = "#2f6fed"
    elif score >= 40:
        color = "#b7791f"
    else:
        color = "#d92d20"
    return (
        f"<div class='scorebar'><div style='width:{score:.1f}%;background:{color};'></div></div>"
        f"<span class='scoretext'>{score:.1f}/100</span>"
    )


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
        for date_col in ["月份", "日期", "month", "date"]:
            if date_col in rows.columns:
                rows = rows.copy()
                rows["_sort_date"] = pd.to_datetime(rows[date_col], errors="coerce")
                rows = rows.sort_values("_sort_date")
                break
        return {str(k): v for k, v in rows.iloc[-1].to_dict().items() if pd.notna(v)}
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


def run_weighted_signal_backtest(hist, params, profile):
    adjusted = dict(params)
    if profile == "品質價值強化":
        adjusted["rvol"] = max(params["rvol"] - 0.2, 1.0)
        adjusted["max_atr"] = max(params["max_atr"] - 0.7, 1.0)
        adjusted["stop"] = max(params["stop"] - 1.0, 1.0)
    elif profile == "動能突破強化":
        adjusted["rvol"] = params["rvol"] + 0.4
        adjusted["target"] = params["target"] + 4.0
        adjusted["trailing"] = max(params["trailing"] - 1.0, 2.0)
    elif profile == "風控防守強化":
        adjusted["max_atr"] = max(params["max_atr"] - 1.0, 1.0)
        adjusted["stop"] = max(params["stop"] - 2.0, 1.0)
        adjusted["target"] = max(params["target"] - 2.0, 2.0)
    return run_signal_backtest(hist, adjusted)


def stats_score(stats):
    if not stats or "交易次數" not in stats or stats["交易次數"] == 0:
        return -999
    return (
        stats.get("平均淨報酬%", 0) * 2
        + stats.get("勝率%", 0) * 0.08
        + stats.get("獲利因子", 0) * 2
        + stats.get("最佳單筆%", 0) * 0.2
        + stats.get("最差單筆%", 0) * 0.5
        + stats.get("平均最大回撤%", 0) * 0.3
    )


def run_walk_forward_calibration(hist, base_params, train_days=252, test_days=63):
    df = hist.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    profiles = ["原始權重", "品質價值強化", "動能突破強化", "風控防守強化"]
    test_days = max(test_days, 126)
    min_needed = train_days + test_days + 80
    if len(df) < min_needed:
        return pd.DataFrame(), pd.DataFrame(), {"狀態": f"資料不足，至少需要約 {min_needed} 個交易日"}

    rows = []
    test_trades = []
    start = 0
    segment = 1
    while start + train_days + test_days <= len(df):
        train = df.iloc[start : start + train_days]
        test = df.iloc[start + train_days : start + train_days + test_days]
        train_scores = []
        for profile in profiles:
            _, train_stats = run_weighted_signal_backtest(train, base_params, profile)
            train_scores.append((profile, stats_score(train_stats), train_stats))
        best_profile, train_score, train_stats = sorted(train_scores, key=lambda item: item[1], reverse=True)[0]
        test_df, test_stats = run_weighted_signal_backtest(test, base_params, best_profile)
        if not test_df.empty:
            test_df = test_df.copy()
            test_df["段次"] = segment
            test_df["採用輪廓"] = best_profile
            test_trades.append(test_df)
        rows.append(
            {
                "段次": segment,
                "訓練起": train.index[0].date(),
                "訓練迄": train.index[-1].date(),
                "測試起": test.index[0].date(),
                "測試迄": test.index[-1].date(),
                "訓練最佳輪廓": best_profile,
                "訓練分數": round(train_score, 2),
                "訓練交易數": train_stats.get("交易次數", 0),
                "測試交易數": test_stats.get("交易次數", 0),
                "測試勝率%": test_stats.get("勝率%", 0),
                "測試平均淨報酬%": test_stats.get("平均淨報酬%", 0),
                "測試獲利因子": test_stats.get("獲利因子", 0),
                "測試最差單筆%": test_stats.get("最差單筆%", 0),
            }
        )
        start += test_days
        segment += 1

    walk_df = pd.DataFrame(rows)
    all_trades = pd.concat(test_trades, ignore_index=True) if test_trades else pd.DataFrame()
    if walk_df.empty:
        return walk_df, all_trades, {"狀態": "沒有可顯示的 walk-forward 結果"}
    summary = {
        "段數": len(walk_df),
        "測試總交易數": int(walk_df["測試交易數"].sum()),
        "平均測試勝率%": round(walk_df["測試勝率%"].mean(), 1),
        "平均測試淨報酬%": round(walk_df["測試平均淨報酬%"].mean(), 2),
        "平均測試獲利因子": round(walk_df["測試獲利因子"].mean(), 2),
        "最差測試單筆%": round(walk_df["測試最差單筆%"].min(), 2),
    }
    return walk_df, all_trades, summary


def hitl_recommendations(style, mode):
    base = ["股號", "產業", "同業排名", "財報備註"]
    if mode == "白馬模式":
        base += ["月份", "營收", "EPS", "淨利", "ROE", "ROA", "ROIC", "毛利率", "營益率", "淨利率", "負債權益比", "流動比率", "利息保障倍數", "自由現金流", "FCF殖利率", "PE分位", "PB分位", "配息率"]
    else:
        base += ["營收YoY", "EPSYoY", "分析師上修", "法人買超", "主力籌碼", "產業強度", "突破型態備註", "事件催化"]
    if style == "當沖":
        base += ["盤中催化", "新聞時間", "券資變化", "隔日沖風險"]
    return base


def build_hitl_template(style, mode):
    columns = hitl_recommendations(style, mode)
    sample = {column: "" for column in columns}
    sample["股號"] = "2330.TW"
    if "月份" in sample:
        sample["月份"] = "2026-05"
    if "ROE" in sample:
        sample.update({"營收": 200000000000, "EPS": 10.5, "淨利": 85000000000, "ROE": 25, "ROA": 12, "ROIC": 18, "毛利率": 55, "營益率": 42, "淨利率": 38})
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


FACTOR_LABELS = {
    "value": "估值 Value",
    "growth": "成長 Growth",
    "quality": "品質 Quality",
    "momentum": "動能 Momentum",
    "low_vol": "低波動 Low Vol",
    "liquidity": "流動性 Liquidity",
    "risk": "風控 Risk",
    "dividend_safety": "股利安全 Dividend",
}


FACTOR_REASON_TEXT = {
    "value": ("估值相對合理或現金流殖利率具吸引力", "估值偏貴、分位偏高或自由現金流不足"),
    "growth": ("營收、盈餘或中期報酬動能支持成長評價", "成長動能不足或缺少上修訊號"),
    "quality": ("ROE/ROA/ROIC、利潤率與負債結構支持企業品質", "獲利品質、資本效率或負債結構不足"),
    "momentum": ("相對強弱、均線斜率、RSI/MACD/ADX 與量能形成動能共振", "趨勢、量能或突破品質尚未成形"),
    "low_vol": ("ATR、布林寬度與跳空風險處於可控範圍", "波動、跳空或價格震盪風險偏高"),
    "liquidity": ("成交量、成交金額與 RVOL 足以支撐進出場", "流動性不足，可能放大滑價與出場風險"),
    "risk": ("財務、波動、流動性與失敗防護條件較完整", "風控條件不足或已有否決訊號"),
    "dividend_safety": ("殖利率、配息率、FCF 與利息保障支撐股利安全", "股利缺乏現金流或盈餘覆蓋"),
}


def inject_wallwin_styles():
    st.markdown(
        """
        <style>
        :root {
            --ww-border: #e5e7eb;
            --ww-muted: #667085;
            --ww-ink: #1f2937;
            --ww-soft: #f8fafc;
            --ww-blue: #1d4ed8;
        }
        .block-container { padding-top: 1.4rem; }
        h2, h3, h4 { letter-spacing: 0 !important; color: var(--ww-ink); }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--ww-border);
            border-radius: 8px;
            padding: 14px 16px;
            min-height: 96px;
        }
        div[data-testid="stMetricLabel"] p {
            color: var(--ww-muted);
            font-size: 0.82rem;
            line-height: 1.25;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.45rem;
            line-height: 1.2;
            color: var(--ww-ink);
        }
        .ww-section {
            margin: 18px 0 10px;
            padding: 12px 14px;
            border-left: 4px solid var(--ww-blue);
            background: var(--ww-soft);
            border-radius: 6px;
        }
        .ww-section-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--ww-ink);
            margin: 0;
        }
        .ww-card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin: 10px 0 18px;
        }
        .ww-card {
            border: 1px solid var(--ww-border);
            border-radius: 8px;
            padding: 14px 15px;
            background: #fff;
            min-height: 92px;
        }
        .ww-card-label {
            color: var(--ww-muted);
            font-size: 0.78rem;
            line-height: 1.3;
            margin-bottom: 8px;
        }
        .ww-card-value {
            color: var(--ww-ink);
            font-size: 1.28rem;
            line-height: 1.2;
            font-weight: 650;
            overflow-wrap: anywhere;
        }
        .ww-card-note {
            margin-top: 7px;
            color: var(--ww-muted);
            font-size: 0.78rem;
            line-height: 1.35;
        }
        .ww-hero {
            border: 1px solid var(--ww-border);
            border-radius: 8px;
            padding: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            margin: 10px 0 14px;
        }
        .ww-hero-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 6px;
        }
        .ww-hero-body {
            color: var(--ww-muted);
            font-size: 0.92rem;
            line-height: 1.55;
        }
        .scorebar {
            width: 120px;
            height: 8px;
            background: #eef2f7;
            border-radius: 999px;
            display: inline-block;
            overflow: hidden;
            vertical-align: middle;
            margin-right: 8px;
        }
        .scorebar > div { height: 100%; border-radius: 999px; }
        .scoretext {
            color: var(--ww-ink);
            font-size: 0.86rem;
            font-weight: 650;
        }
        .stDataFrame { font-size: 0.92rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title, caption=""):
    st.markdown(
        f"<div class='ww-section'><p class='ww-section-title'>{escape(title)}</p>"
        f"{f'<div class=\"ww-card-note\">{escape(caption)}</div>' if caption else ''}</div>",
        unsafe_allow_html=True,
    )


def render_card_grid(values, notes=None):
    notes = notes or {}
    cards = []
    for label, value in values.items():
        note = notes.get(label, "")
        cards.append(
            "<div class='ww-card'>"
            f"<div class='ww-card-label'>{escape(str(label))}</div>"
            f"<div class='ww-card-value'>{escape(str(value))}</div>"
            f"{f'<div class=\"ww-card-note\">{escape(str(note))}</div>' if note else ''}"
            "</div>"
        )
    st.markdown(f"<div class='ww-card-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def render_explain_box(title, body):
    st.markdown(
        f"<div class='ww-hero'><div class='ww-hero-title'>{escape(title)}</div>"
        f"<div class='ww-hero-body'>{escape(body)}</div></div>",
        unsafe_allow_html=True,
    )


def build_stock_dashboard_rows(symbol, info, hist, engine, light, advice, trade_plan):
    df = hist.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) >= 2 else latest
    close = safe_float(latest["Close"])
    prev_close = safe_float(previous["Close"])
    change = close - prev_close
    change_pct = pct_change(close, prev_close)
    amount = safe_float(latest["Close"]) * safe_float(latest["Volume"])
    amplitude = (safe_float(latest["High"]) - safe_float(latest["Low"])) / prev_close * 100 if prev_close else 0
    avg_vol_5 = safe_float(df["Volume"].tail(5).mean())
    avg_vol_20 = safe_float(df["Volume"].tail(20).mean())
    year_high = safe_float(df["High"].tail(252).max())
    year_low = safe_float(df["Low"].tail(252).min())
    m = engine["metrics"]
    board = {
        "識別": {
            "股票代號": symbol,
            "股票名稱": info.get("longName") or info.get("shortName") or symbol,
            "市場": info.get("exchange") or ("TWSE/TPEX" if symbol.endswith((".TW", ".TWO")) else "US/Other"),
            "產業別": info.get("industry") or "N/A",
            "幣別": info.get("currency") or "N/A",
            "資料更新時間": str(df.index[-1]),
        },
        "前一交易日行情": {
            "昨收": fmt_num(prev_close),
            "開盤": fmt_num(latest["Open"]),
            "最高": fmt_num(latest["High"]),
            "最低": fmt_num(latest["Low"]),
            "收盤": fmt_num(close),
            "漲跌": f"{change:+.2f}",
            "漲跌幅": pct_label(change_pct),
            "成交量": fmt_big_number(latest["Volume"]),
            "成交金額": fmt_big_number(amount),
            "振幅": pct_label(amplitude),
            "5日均量": fmt_big_number(avg_vol_5),
            "20日均量": fmt_big_number(avg_vol_20),
            "RVOL": f"{m['rvol']:.2f}x",
        },
        "最近價格摘要": {
            "最新價": fmt_num(close),
            "今日漲跌幅": pct_label(change_pct),
            "今日成交量": fmt_big_number(latest["Volume"]),
            "價格 vs MA20": pct_label(pct_change(close, m["ma20"])),
            "價格 vs MA50": pct_label(pct_change(close, m["ma50"])),
            "價格 vs MA200": pct_label(pct_change(close, m["ma200"])),
            "是否站上 VWAP": "是" if close >= m["vwap"] else "否",
            "52週高點距離": pct_label(pct_change(close, year_high)),
            "52週低點距離": pct_label(pct_change(close, year_low)),
        },
        "WallWin 判讀摘要": {
            "燈號": light,
            "判定": advice,
            "勝率分數": f"{engine['win_score']:.1f} / 100（{engine['bucket']}）",
            "白馬分": f"{engine['white_score']:.1f}",
            "黑馬分": f"{engine['black_score']:.1f}",
            "主要加分因子": "、".join(FACTOR_LABELS.get(k, k) for k in sorted(engine["factor_scores"], key=engine["factor_scores"].get, reverse=True)[:3]),
            "主要扣分因子": "、".join(FACTOR_LABELS.get(k, k) for k in sorted(engine["factor_scores"], key=engine["factor_scores"].get)[:3]),
            "否決條件": "、".join(engine["hard_flags"]) if engine["hard_flags"] else "無",
            "建議交易週期": engine["style"],
            "建議模式": engine["mode"],
            "交易計畫摘要": f"進場 {trade_plan['entry']:.2f} / 停損 {trade_plan['stop']:.2f} / 目標一 {trade_plan['target_1']:.2f}",
        },
    }
    return board


def render_key_value_board(title, values, columns=4):
    render_section_header(title)
    render_card_grid(values)


def score_cell(score):
    return f"{clamp(score):.1f}/100"


def build_fundamental_reason_table(engine):
    m = engine["metrics"]
    rows = [
        {
            "類別": "估值",
            "指標": "P/E",
            "數值": fmt_num(m["pe"]),
            "得分": score_cell(score_low(m["pe"], 10, 35)),
            "理由": score_reason(score_low(m["pe"], 10, 35), "本益比位於相對便宜區間", "本益比偏高或獲利支撐不足"),
        },
        {
            "類別": "估值",
            "指標": "P/B",
            "數值": fmt_num(m["pb"]),
            "得分": score_cell(score_low(m["pb"], 1.0, 5.0)),
            "理由": score_reason(score_low(m["pb"], 1.0, 5.0), "股價淨值比相對合理", "股價淨值比偏高，安全邊際不足"),
        },
        {
            "類別": "估值",
            "指標": "P/S",
            "數值": fmt_num(m["ps"]),
            "得分": score_cell(score_low(m["ps"], 1.0, 8.0)),
            "理由": score_reason(score_low(m["ps"], 1.0, 8.0), "營收估值相對合理", "營收估值偏高，需更強成長支撐"),
        },
        {
            "類別": "估值",
            "指標": "EV/EBITDA",
            "數值": fmt_num(m["ev_ebitda"]),
            "得分": score_cell(score_low(m["ev_ebitda"], 6, 25)),
            "理由": score_reason(score_low(m["ev_ebitda"], 6, 25), "企業價值相對營運獲利合理", "企業價值倍數偏高"),
        },
        {
            "類別": "品質",
            "指標": "ROE",
            "數值": fmt_num(m["roe"], suffix="%"),
            "得分": score_cell(score_high(m["roe"], 5, 25)),
            "理由": score_reason(score_high(m["roe"], 5, 25), "股東權益報酬率具品質支撐", "股東權益報酬率不足"),
        },
        {
            "類別": "品質",
            "指標": "ROA",
            "數值": fmt_num(m["roa"], suffix="%"),
            "得分": score_cell(score_high(m["roa"], 2, 12)),
            "理由": score_reason(score_high(m["roa"], 2, 12), "資產使用效率良好", "資產報酬偏弱"),
        },
        {
            "類別": "品質",
            "指標": "ROIC",
            "數值": fmt_num(m["roic"], suffix="%"),
            "得分": score_cell(score_high(m["roic"], 5, 20)),
            "理由": score_reason(score_high(m["roic"], 5, 20), "投入資本報酬具護城河線索", "投入資本報酬不足"),
        },
        {
            "類別": "股利",
            "指標": "殖利率",
            "數值": fmt_num(m["dividend_yield"], suffix="%"),
            "得分": score_cell(score_high(m["dividend_yield"], 1, 6)),
            "理由": score_reason(score_high(m["dividend_yield"], 1, 6), "殖利率具現金回報吸引力", "殖利率不足或缺乏配息吸引力"),
        },
        {
            "類別": "現金流",
            "指標": "FCF Yield",
            "數值": fmt_num(m["fcf_yield"], suffix="%"),
            "得分": score_cell(score_high(m["fcf_yield"], 0, 8)),
            "理由": score_reason(score_high(m["fcf_yield"], 0, 8), "自由現金流殖利率支持估值", "自由現金流不足或估值支撐弱"),
        },
    ]
    return pd.DataFrame(rows)


def build_technical_reason_table(engine):
    m = engine["metrics"]
    rows = [
        {
            "指標": "RSI",
            "數值": fmt_num(m["rsi"], 1),
            "得分": score_cell(score_range(m["rsi"], 45, 72, 2.0)),
            "理由": score_reason(score_range(m["rsi"], 45, 72, 2.0), "RSI 位於健康偏強區間", "RSI 過弱或過熱，追價風險提高"),
        },
        {
            "指標": "MACD Diff",
            "數值": fmt_num(m["macd_diff"], 2),
            "得分": score_cell(100 if m["macd_diff"] > 0 else 30),
            "理由": "MACD Diff 大於 0 代表短線動能偏多。" if m["macd_diff"] > 0 else "MACD Diff 低於 0，短線動能仍偏弱。",
        },
        {
            "指標": "ADX",
            "數值": fmt_num(m["adx"], 1),
            "得分": score_cell(score_high(m["adx"], 12, 35)),
            "理由": score_reason(score_high(m["adx"], 12, 35), "ADX 顯示趨勢強度足夠", "ADX 偏低，趨勢方向不夠明確"),
        },
        {
            "指標": "RVOL",
            "數值": f"{m['rvol']:.2f}x",
            "得分": score_cell(score_high(m["rvol"], 0.8, 2.5)),
            "理由": score_reason(score_high(m["rvol"], 0.8, 2.5), "相對成交量放大，量能支持訊號", "相對成交量不足，突破可信度較低"),
        },
        {
            "指標": "ATR%",
            "數值": fmt_num(m["atr_pct"], 2, "%"),
            "得分": score_cell(score_low(m["atr_pct"], 2.5, 9.0)),
            "理由": score_reason(score_low(m["atr_pct"], 2.5, 9.0), "波動仍在可控區間", "波動過高，停損與滑價風險提高"),
        },
        {
            "指標": "VCP",
            "數值": fmt_num(m["vcp"], 2, "%"),
            "得分": score_cell(score_low(m["vcp"], 4, 18)),
            "理由": score_reason(score_low(m["vcp"], 4, 18), "波動收縮明顯，具突破前整理特徵", "波動尚未有效收縮"),
        },
        {
            "指標": "52週高點距離",
            "數值": fmt_num(m["dist_52w_high"], 2, "%"),
            "得分": score_cell(score_low(abs(m["dist_52w_high"]), 0, 35)),
            "理由": score_reason(score_low(abs(m["dist_52w_high"]), 0, 35), "價格接近 52 週高點，強勢特徵較明顯", "距離高點較遠，強勢確認不足"),
        },
    ]
    return pd.DataFrame(rows)


def render_stock_dashboard(symbol, info, hist, engine, light, advice, trade_plan):
    st.subheader("個股資訊看板")
    render_explain_box(
        "閱讀順序",
        "先看 WallWin 燈號與否決條件，再看價格是否站上關鍵均線與 VWAP，最後用基本面與技術面摘要確認分數來源。",
    )
    board = build_stock_dashboard_rows(symbol, info, hist, engine, light, advice, trade_plan)
    render_key_value_board("A. 個股識別", board["識別"], columns=3)
    render_key_value_board("B. 前一交易日行情", board["前一交易日行情"], columns=4)
    render_key_value_board("C. 即時/最近價格摘要", board["最近價格摘要"], columns=3)
    render_key_value_board("F. WallWin 判讀摘要", board["WallWin 判讀摘要"], columns=3)
    render_score_breakdown(engine)

    with st.expander("D. 基本面摘要", expanded=False):
        st.dataframe(build_fundamental_reason_table(engine), width="stretch", hide_index=True)
    with st.expander("E. 技術面摘要", expanded=False):
        st.dataframe(build_technical_reason_table(engine), width="stretch", hide_index=True)


def build_factor_matrix(engine):
    weights = WEIGHTS[engine["mode"]][engine["style"]]
    active_weight_avg = sum(weights.values()) / max(len(weights), 1)
    rows = []
    for key, score in engine["factor_scores"].items():
        weight = weights.get(key, 0)
        relative_score = score - 50
        relative_weight = weight - active_weight_avg
        rows.append(
            {
                "因子": FACTOR_LABELS.get(key, key),
                "分數": round(score, 1),
                "分數意義": interpret_score(score),
                "相對分數": round(relative_score, 1),
                "相對分數判讀": interpret_relative(relative_score),
                "權重": round(weight, 3),
                "相對權重": round(relative_weight, 3),
                "相對權重判讀": interpret_relative(relative_weight * 100, "%"),
                "加權貢獻": round(score * weight, 2),
                "得分理由": score_reason(score, *FACTOR_REASON_TEXT.get(key, ("條件支持評價", "條件不足"))),
            }
        )
    return pd.DataFrame(rows).sort_values("加權貢獻", ascending=False)


def build_score_breakdown(engine, target_mode):
    weights = WEIGHTS[target_mode][engine["style"]]
    rows = []
    for key, weight in weights.items():
        score = engine["factor_scores"].get(key, 0)
        rows.append(
            {
                "因子": FACTOR_LABELS.get(key, key),
                "因子分數": round(score, 1),
                "權重": f"{weight:.0%}",
                "加權貢獻": round(score * weight, 2),
                "理由": score_reason(score, *FACTOR_REASON_TEXT.get(key, ("條件支持評價", "條件不足"))),
            }
        )
    return pd.DataFrame(rows).sort_values("加權貢獻", ascending=False)


def render_score_breakdown(engine):
    render_section_header("評分理由拆解", "白馬分與黑馬分皆由同一批因子分數，套用不同模式權重後加總。")
    score_cols = st.columns(2)
    with score_cols[0]:
        st.markdown("#### 白馬分計算")
        st.dataframe(build_score_breakdown(engine, "白馬模式"), width="stretch", hide_index=True)
    with score_cols[1]:
        st.markdown("#### 黑馬分計算")
        st.dataframe(build_score_breakdown(engine, "黑馬模式"), width="stretch", hide_index=True)


def render_factor_matrix(engine):
    st.subheader("多因子矩陣")
    render_explain_box(
        "如何閱讀",
        "相對分數以 50 分為中性基準；相對權重代表此模式下該因子是否被特別重視。最後真正影響總分的是「因子分數 × 權重」得到的加權貢獻。",
    )
    factor_df = build_factor_matrix(engine)
    st.dataframe(factor_df, width="stretch", hide_index=True)
    chart_df = factor_df.set_index("因子")[["分數", "加權貢獻"]]
    st.bar_chart(chart_df)
    render_score_breakdown(engine)


def build_fundamental_trend_from_hitl(advanced_df, symbol):
    if advanced_df is None or advanced_df.empty:
        return pd.DataFrame()
    normalized = normalize_symbol_for_advanced(symbol)
    df = advanced_df.copy()
    cols = {str(col).strip(): col for col in df.columns}
    symbol_col = cols.get("股號") or cols.get("symbol") or cols.get("Symbol")
    date_col = cols.get("月份") or cols.get("日期") or cols.get("month") or cols.get("date")
    if symbol_col is None or date_col is None:
        return pd.DataFrame()
    df = df[df[symbol_col].astype(str).str.upper().str.replace(".TW", "", regex=False).str.replace(".TWO", "", regex=False) == normalized]
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["月份"] = pd.to_datetime(df[date_col], errors="coerce").dt.to_period("M").dt.to_timestamp()
    df = df.dropna(subset=["月份"]).sort_values("月份")
    value_columns = []
    for name in ["營收", "EPS", "淨利", "毛利率", "營益率", "淨利率", "ROE", "ROA", "ROIC", "自由現金流", "FCF"]:
        if name in df.columns:
            value_columns.append(name)
    rows = []
    for col in value_columns:
        series = pd.to_numeric(df[col], errors="coerce")
        for idx, value in series.items():
            month = df.loc[idx, "月份"]
            prev_month = series.shift(1).loc[idx]
            prev_year = series.shift(12).loc[idx]
            rows.append(
                {
                    "月份": month.strftime("%Y-%m"),
                    "指標": col,
                    "數值": round(safe_float(value), 2),
                    "MoM%": round(pct_change(safe_float(value), safe_float(prev_month)), 2) if pd.notna(prev_month) else None,
                    "YoY%": round(pct_change(safe_float(value), safe_float(prev_year)), 2) if pd.notna(prev_year) else None,
                    "增減率判讀": "改善" if pd.notna(prev_month) and safe_float(value) >= safe_float(prev_month) else "轉弱/待觀察",
                }
            )
    return pd.DataFrame(rows)


def render_fundamental_trend(advanced_data, symbol, engine):
    st.subheader("白馬基本面月度矩陣")
    st.caption("0 成本資料源通常缺少台股月營收與完整月度財務；若上傳 HITL 月資料，系統會自動計算 MoM、YoY 與增減率。")
    period_years = st.slider("比較年限", 3, 5, 3, key="fundamental_years")
    trend_df = build_fundamental_trend_from_hitl(advanced_data, symbol)
    if trend_df.empty:
        m = engine["metrics"]
        st.info("尚未偵測到月度 HITL 基本面資料。請上傳含「股號、月份、營收、EPS、淨利、毛利率、營益率、淨利率、ROE、ROIC」的 CSV。")
        st.dataframe(
            pd.DataFrame(
                [
                    {"指標": "營收 YoY", "目前值": fmt_num(m["revenue_growth"], suffix="%"), "資料狀態": "yfinance/上傳資料可用時顯示"},
                    {"指標": "EPS YoY", "目前值": fmt_num(m["earnings_growth"], suffix="%"), "資料狀態": "yfinance/上傳資料可用時顯示"},
                    {"指標": "ROE", "目前值": fmt_num(m["roe"], suffix="%"), "資料狀態": "目前快照"},
                    {"指標": "毛利率", "目前值": fmt_num(m["gross_margin"], suffix="%"), "資料狀態": "目前快照"},
                    {"指標": "FCF Yield", "目前值": fmt_num(m["fcf_yield"], suffix="%"), "資料狀態": "目前快照"},
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        return
    cutoff = (pd.Timestamp.today() - pd.DateOffset(years=period_years)).strftime("%Y-%m")
    trend_df = trend_df[trend_df["月份"] >= cutoff]
    st.dataframe(trend_df, width="stretch", hide_index=True)
    chart_source = trend_df.pivot_table(index="月份", columns="指標", values="數值", aggfunc="last")
    st.line_chart(chart_source)


def render_technical_charts(hist, symbol):
    st.subheader("黑馬技術線圖")
    years = st.slider("技術圖比較年限", 2, 5, 2, key="technical_years")
    chart_df = hist.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"]).tail(252 * years)
    if chart_df.empty:
        st.warning("沒有足夠價格資料可繪製技術圖。")
        return
    chart_df = chart_df.copy()
    chart_df["MA20"] = chart_df["Close"].rolling(20).mean()
    chart_df["MA50"] = chart_df["Close"].rolling(50).mean()
    chart_df["MA200"] = chart_df["Close"].rolling(200).mean()
    chart_df["RSI"] = ta.momentum.RSIIndicator(close=chart_df["Close"]).rsi()
    chart_df["MACD"] = ta.trend.MACD(close=chart_df["Close"]).macd_diff()
    chart_df["RVOL"] = chart_df["Volume"] / chart_df["Volume"].rolling(20).mean()
    if go is None or make_subplots is None:
        st.line_chart(chart_df[["Close", "MA20", "MA50", "MA200"]])
        st.bar_chart(chart_df[["Volume"]])
        return
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.50, 0.18, 0.16, 0.16],
        subplot_titles=("K線 + MA20/MA50/MA200", "成交量", "RSI", "MACD Diff"),
    )
    fig.add_trace(go.Candlestick(x=chart_df.index, open=chart_df["Open"], high=chart_df["High"], low=chart_df["Low"], close=chart_df["Close"], name="K線"), row=1, col=1)
    for ma_name in ["MA20", "MA50", "MA200"]:
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df[ma_name], mode="lines", name=ma_name), row=1, col=1)
    fig.add_trace(go.Bar(x=chart_df.index, y=chart_df["Volume"], name="成交量"), row=2, col=1)
    fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["RSI"], mode="lines", name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", row=3, col=1)
    fig.add_trace(go.Bar(x=chart_df.index, y=chart_df["MACD"], name="MACD Diff"), row=4, col=1)
    fig.update_layout(height=850, xaxis_rangeslider_visible=False, showlegend=True)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(
        chart_df[["Close", "MA20", "MA50", "MA200", "RSI", "MACD", "RVOL"]].tail(30).round(2),
        width="stretch",
    )


def render_backtest_guide(stats, trades_df):
    render_explain_box("策略回測的功能", "回答「如果過去照這套訊號進出，勝率、報酬、風險與持有天數大約如何」。它不是保證未來，而是用來檢查策略是否有紀律與正期望。")
    render_section_header("指標怎麼讀")
    guide = pd.DataFrame(
        [
            {"指標": "交易次數", "意思": "符合進場條件並完成出場的交易筆數", "應用": "太少代表樣本不足，結論要保守"},
            {"指標": "勝率", "意思": "淨報酬大於 0 的交易比例", "應用": "需搭配獲利因子，不可單看勝率"},
            {"指標": "平均淨報酬", "意思": "扣除交易成本與滑價後，每筆平均報酬", "應用": "大於 0 才有基本正期望"},
            {"指標": "獲利因子", "意思": "總獲利 / 總虧損絕對值", "應用": "大於 1 代表回測總獲利高於總虧損"},
            {"指標": "平均最大回撤", "意思": "進場後期間內平均最深浮虧", "應用": "用來評估心理壓力與停損是否合理"},
        ]
    )
    st.dataframe(guide, width="stretch", hide_index=True)
    if not trades_df.empty:
        st.markdown("#### 表格欄位怎麼來")
        st.caption("訊號日由策略條件產生；進場日採下一交易日開盤；出場日由停損、停利、移動停損或持有期滿決定；淨報酬已扣除雙邊成本。")


def render_walk_forward_guide():
    render_explain_box("Walk-forward 的功能", "先用訓練期挑參數或輪廓，再拿下一段測試期驗證，較能降低只對單一歷史區間過度最佳化的風險。")
    st.dataframe(
        pd.DataFrame(
            [
                {"欄位": "訓練起/訓練迄", "意思": "用來挑最佳權重輪廓的歷史區間"},
                {"欄位": "測試起/測試迄", "意思": "不用來挑參數，只用來驗證下一段表現"},
                {"欄位": "採用輪廓", "意思": "訓練期表現最佳的權重設定"},
                {"欄位": "測試勝率/淨報酬/獲利因子", "意思": "該輪廓在下一段測試區間的實際回測結果"},
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def render_trade_plan(engine, trade_plan, light, advice):
    st.subheader("交易計畫書")
    st.caption("以使用者可執行為核心：先看是否允許交易，再看價格、風險、部位與檢查清單。")
    decision_cols = st.columns(4)
    decision_cols[0].metric("執行狀態", light)
    decision_cols[1].metric("風險報酬比", f"{trade_plan.get('rr', 0):.2f}R")
    decision_cols[2].metric("勝率分數", f"{engine['win_score']:.1f}")
    decision_cols[3].metric("分級", engine["bucket"])
    st.info(advice)

    price_cols = st.columns(4)
    price_cols[0].metric("進場/觀察", f"{trade_plan['entry']:.2f}")
    price_cols[1].metric("停損", f"{trade_plan['stop']:.2f}")
    price_cols[2].metric("目標一", f"{trade_plan['target_1']:.2f}")
    price_cols[3].metric("目標二", f"{trade_plan['target_2']:.2f}")

    plan_df = pd.DataFrame(
        [
            {"項目": "進場條件", "內容": "分數與燈號符合，且價格沒有跌破主要風控線"},
            {"項目": "加碼條件", "內容": "突破後站穩、RVOL 延續、未出現爆量長上影"},
            {"項目": "減碼條件", "內容": "達目標一可先落袋部分，剩餘部位改用移動停損"},
            {"項目": "停損條件", "內容": "跌破停損價、跌破 VWAP/突破K低點、或否決條件成立"},
            {"項目": "禁止事項", "內容": "禁止無計畫攤平，禁止取消停損，禁止忽略財報/重大消息風險"},
            {"項目": "部位建議", "內容": trade_plan["position_hint"]},
        ]
    )
    st.dataframe(plan_df, width="stretch", hide_index=True)

    checklist = pd.DataFrame(
        [
            {"檢查": "我知道最大可能虧損是多少", "狀態": "交易前確認"},
            {"檢查": "停損價已先寫好，不臨場改口", "狀態": "交易前確認"},
            {"檢查": "若同日停損/停利同時觸發，採保守停損", "狀態": "回測假設"},
            {"檢查": "若出現否決條件，暫停新倉位", "狀態": "風控規則"},
        ]
    )
    st.markdown("#### 交易前檢查清單")
    st.dataframe(checklist, width="stretch", hide_index=True)


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


def render_wallwin_glossary():
    st.subheader("WallWin 小辭典")
    st.caption("整理本系統會出現的股市、投資、技術分析、回測與風控名詞，包含解釋、公式與案例。")

    glossary_df = pd.DataFrame(WALLWIN_GLOSSARY)
    search_col, category_col = st.columns([2, 1])
    keyword = search_col.text_input("搜尋名詞", placeholder="例如：ROE、RVOL、停損、Walk-forward")
    categories = ["全部"] + sorted(glossary_df["category"].unique().tolist())
    selected_category = category_col.selectbox("分類", categories)

    filtered = glossary_df.copy()
    if selected_category != "全部":
        filtered = filtered[filtered["category"] == selected_category]
    if keyword.strip():
        key = keyword.strip().lower()
        filtered = filtered[
            filtered.apply(
                lambda row: key in " ".join(str(row[col]).lower() for col in ["category", "term", "formula", "explain", "example"]),
                axis=1,
            )
        ]

    metric_cols = st.columns(3)
    metric_cols[0].metric("收錄名詞", len(glossary_df))
    metric_cols[1].metric("目前顯示", len(filtered))
    metric_cols[2].metric("分類數", glossary_df["category"].nunique())

    st.dataframe(
        filtered[["category", "term", "formula"]].rename(columns={"category": "分類", "term": "名詞", "formula": "公式/判讀"}),
        width="stretch",
        hide_index=True,
    )

    st.download_button(
        "下載 WallWin 小辭典 CSV",
        glossary_df.rename(columns={"category": "分類", "term": "名詞", "formula": "公式/判讀", "explain": "解釋", "example": "案例"}).to_csv(index=False).encode("utf-8-sig"),
        "wallwin_glossary.csv",
        "text/csv",
    )

    for category in sorted(filtered["category"].unique().tolist()):
        category_rows = filtered[filtered["category"] == category]
        st.markdown(f"### {category}")
        for _, row in category_rows.iterrows():
            with st.expander(row["term"]):
                st.markdown(f"**解釋：** {row['explain']}")
                st.markdown(f"**公式/判讀：** `{row['formula']}`")
                st.markdown(f"**案例：** {row['example']}")


st.set_page_config(page_title=APP_TITLE, layout="wide")
inject_wallwin_styles()
st.title("💎 " + APP_TITLE)
st.caption(APP_MISSION)
st.caption(DISCLAIMER)
require_app_password()

st.sidebar.header("⚙️ 投審控制台")
ai_api_key, ai_key_source = resolve_ai_api_key()
symbol = normalize_symbol(st.sidebar.text_input("🎯 目標股號", "2206.TW"))
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

analyze_button = st.sidebar.button("🚀 啟動多因子投審", type="primary", width="stretch")

st.sidebar.markdown("---")
st.sidebar.subheader("📡 Watchlist 多檔掃描")
watchlist_symbols = st.sidebar.text_area("股票清單", "2330.TW, 2317.TW, 2454.TW, 2206.TW", height=80)
scan_button = st.sidebar.button("📡 掃描 Watchlist", width="stretch")

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
    st.dataframe(result_df, width="stretch", hide_index=True)
    st.download_button("下載 Watchlist CSV", result_df.to_csv(index=False).encode("utf-8-sig"), "wallwin_watchlist.csv", "text/csv")

if analyze_button:
    hist = load_history(symbol, period="1y")
    hist_long = load_history(symbol, period="5y")
    if not hist_long.empty:
        hist = hist_long.tail(252) if len(hist_long) >= 252 else hist
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

    render_stock_dashboard(symbol, info, hist, engine, light, advice, trade_plan)
    st.markdown("---")

    tab_matrix, tab_fundamental, tab_technical, tab_backtest, tab_calibration, tab_plan, tab_ai, tab_glossary = st.tabs(["多因子矩陣", "白馬基本面", "黑馬技術面", "策略回測", "權重校準", "交易計畫", "AI 報告", "WallWin 小辭典"])
    with tab_matrix:
        render_factor_matrix(engine)
        if engine["hard_flags"]:
            st.error("否決條件：" + "、".join(engine["hard_flags"]))
    with tab_fundamental:
        render_explain_box("白馬模式定位", "白馬模式不是只等於基本面，但核心偏向企業品質、估值、現金流、財務安全與股利安全；技術面主要作為風險確認。")
        render_section_header("基本面評分理由", "每個指標皆以 0-100 分轉換，最後匯入 Value、Quality、Dividend Safety 等因子。")
        st.dataframe(build_fundamental_reason_table(engine), width="stretch", hide_index=True)
        render_fundamental_trend(advanced_data, symbol, engine)
    with tab_technical:
        render_explain_box("黑馬模式定位", "黑馬模式不是只等於技術面，但核心偏向趨勢、量價、相對強弱、突破品質與失敗防護；基本面主要作為風險過濾。")
        render_section_header("技術面評分理由", "先看趨勢與量能是否同步，再看波動風險是否可控。")
        st.dataframe(build_technical_reason_table(engine), width="stretch", hide_index=True)
        render_technical_charts(hist_long if not hist_long.empty else hist, symbol)
        render_card_grid(
            {
                "相對強弱": f"{m['rel_strength']:.2f}%",
                "MA50 slope": f"{m['ma50_slope']:.2f}%",
                "MA200 slope": f"{m['ma200_slope']:.2f}%",
                "52週高點距離": f"{m['dist_52w_high']:.2f}%",
                "VWAP": f"{m['vwap']:.2f}",
                "Gap": f"{m['gap_pct']:.2f}%",
                "上影線": f"{m['upper_shadow']:.2f}%",
            }
        )
        if style == "當沖" and daytrade and daytrade.get("available"):
            render_card_grid(
                {
                    "當沖 VWAP": f"{daytrade['intraday_vwap']:.2f}",
                    "5m RVOL": f"{daytrade['intraday_rvol']:.2f}x",
                    "5m RSI": f"{daytrade['rsi_5m']:.1f}",
                    "做多分": daytrade["long_bias_score"],
                    "放空分": daytrade["short_bias_score"],
                }
            )
    with tab_backtest:
        st.subheader("策略回測")
        render_explain_box("新手閱讀順序", "先看交易次數是否足夠，再看平均淨報酬與獲利因子，最後看最大回撤能不能承受。回測是策略體檢，不是未來獲利保證。")
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
            render_backtest_guide(stats, trades_df)
            stat_cols = st.columns(4)
            stat_cols[0].metric("交易次數", stats["交易次數"])
            stat_cols[1].metric("勝率", f"{stats['勝率%']:.1f}%")
            stat_cols[2].metric("平均淨報酬", f"{stats['平均淨報酬%']:.2f}%")
            stat_cols[3].metric("獲利因子", f"{stats['獲利因子']:.2f}")
            st.caption("採下一交易日開盤進場，逐日檢查停損、停利、移動停損；同日停損/停利同時觸發時採保守停損。")
            st.dataframe(trades_df.tail(40), width="stretch", hide_index=True)
            st.download_button("下載回測 CSV", trades_df.to_csv(index=False).encode("utf-8-sig"), f"{symbol}_backtest.csv", "text/csv")
    with tab_calibration:
        st.subheader("權重校準與輪廓比較")
        render_walk_forward_guide()
        calibration_df = calibrate_weight_profiles(engine)
        st.dataframe(calibration_df, width="stretch", hide_index=True)
        best_profile = calibration_df.iloc[0]
        st.info(
            f"目前資料下最佳輪廓：{best_profile['權重輪廓']}，"
            f"重新加權分數 {best_profile['重新加權分數']:.1f}（{best_profile['分級']}）。"
        )
        st.caption("輪廓比較用於解讀目前標的的因子偏好；下方 walk-forward 會用多年度歷史價格分段驗證。")

        st.markdown("---")
        st.subheader("Walk-forward 多年度回測校準")
        st.caption("0 成本版本使用 yfinance 歷史價格；每段先用訓練期挑最佳輪廓，再到下一段測試期驗證。")
        with st.expander("進階設定", expanded=False):
            wf_period = st.selectbox("歷史資料期間", ["5y", "10y", "max"], index=0)
            train_days = st.slider("訓練窗（交易日）", 126, 504, 252, 21)
            test_days = st.slider("測試窗（交易日）", 126, 252, 126, 21)
        if st.button("執行 walk-forward 校準", type="primary"):
            with st.spinner("正在執行 walk-forward 多年度校準..."):
                wf_hist = load_history(symbol, period=wf_period)
                if wf_hist.empty:
                    st.error("無法取得多年度歷史資料。")
                else:
                    wf_df, wf_trades, wf_summary = run_walk_forward_calibration(wf_hist, bt_params, train_days, test_days)
                    if wf_df.empty:
                        st.warning(wf_summary.get("狀態", "沒有可顯示的 walk-forward 結果"))
                    else:
                        wf_cols = st.columns(5)
                        wf_cols[0].metric("驗證段數", wf_summary["段數"])
                        wf_cols[1].metric("測試交易數", wf_summary["測試總交易數"])
                        wf_cols[2].metric("平均勝率", f"{wf_summary['平均測試勝率%']:.1f}%")
                        wf_cols[3].metric("平均淨報酬", f"{wf_summary['平均測試淨報酬%']:.2f}%")
                        wf_cols[4].metric("平均獲利因子", f"{wf_summary['平均測試獲利因子']:.2f}")
                        st.dataframe(wf_df, width="stretch", hide_index=True)
                        st.download_button(
                            "下載 walk-forward 分段結果 CSV",
                            wf_df.to_csv(index=False).encode("utf-8-sig"),
                            f"{symbol}_walk_forward_segments.csv",
                            "text/csv",
                        )
                        if not wf_trades.empty:
                            st.dataframe(wf_trades.tail(50), width="stretch", hide_index=True)
                            st.download_button(
                                "下載 walk-forward 交易明細 CSV",
                                wf_trades.to_csv(index=False).encode("utf-8-sig"),
                                f"{symbol}_walk_forward_trades.csv",
                                "text/csv",
                            )
    with tab_plan:
        render_trade_plan(engine, trade_plan, light, advice)
    with tab_ai:
        if not ai_api_key:
            st.warning("請在左側輸入使用者自備 Gemini API Key。")
        else:
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
    with tab_glossary:
        render_wallwin_glossary()
