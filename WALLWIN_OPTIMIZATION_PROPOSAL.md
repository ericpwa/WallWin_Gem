# WallWin Gem 功能審查與精進優化建議書

## 1. 審查結論

目前 WallWin Gem 已具備「量化過濾 + LLM 投審演繹 + HITL 人工校準」的決策閉環雛形，但若以「提高股票投資勝率」作為核心使命，現有白馬/黑馬雙軌模型仍不足以稱為完整的華爾街投審等級。

主要原因：

- 白馬模式目前偏重估值倍數，缺少品質、現金流、負債、獲利穩定性、資本效率、產業相對估值。
- 黑馬模式目前偏重量價動能，缺少多週期趨勢、相對強弱、籌碼/流動性、波動風險、型態失敗風控。
- 兩者目前都缺少市場 regime、風險預算、部位 sizing、策略回測驗證、出場紀律與交易成本模型。

因此建議下一階段升級為「多因子投審引擎」，把 Value / Growth / Quality / Momentum / Low Volatility / Liquidity / Risk Control 做成可解釋的分數矩陣。

## 2. 白馬股模式不足

現有方法：

- P/E
- PEG
- P/B
- 股息殖利率

不足處：

- P/E 容易受景氣循環與一次性盈餘扭曲。
- PEG 高度依賴成長率估計，若資料源不穩，分數會失真。
- P/B 對金融、資產股較有意義，對輕資產科技股常失真。
- 缺少 ROE、ROIC、毛利率、營益率、自由現金流、負債比、利息保障倍數。
- 缺少同業比較與歷史估值分位數。
- 缺少「便宜但基本面惡化」的 value trap 過濾。

建議補強：

- Quality：ROE、ROA、ROIC、毛利率、營益率、淨利率、盈餘穩定性。
- Balance Sheet：Debt/Equity、Current Ratio、Interest Coverage。
- Cash Flow：Operating Cash Flow、Free Cash Flow、FCF Yield。
- Valuation：EV/EBITDA、P/S、P/E percentile、P/B percentile。
- Earnings Revision：營收/盈餘 YoY、QoQ、分析師上修/下修，若資料可得。
- Dividend Safety：殖利率、配息率、自由現金流覆蓋率。

## 3. 黑馬股模式不足

現有方法：

- RVOL
- VCP
- RSI
- MACD
- ADX
- VWAP
- MA20/50/200

不足處：

- RVOL 可抓爆量，但無法分辨突破量或出貨量。
- VCP 目前用高低區間壓縮近似，還不是完整型態辨識。
- RSI 單獨使用容易在強勢股過早判定過熱。
- 缺少相對強弱，例如相對大盤/同產業的 RS Rank。
- 缺少多週期確認，例如日線、週線、5 分鐘線訊號一致性。
- 缺少 breakout failure、假突破、gap risk 的否決條件。
- 缺少籌碼集中度、法人買賣、融資融券等本地市場要素。

建議補強：

- Relative Strength：相對大盤 1M/3M/6M 報酬、52 週高點距離。
- Trend Quality：MA slope、higher high / higher low、週線趨勢。
- Breakout Quality：突破前壓縮天數、突破量比、收盤站穩比例。
- Volatility Control：ATR regime、布林帶寬度分位、gap risk。
- Failure Guard：跌破 VWAP、跌破突破K低點、爆量長上影否決。
- Liquidity：成交金額、買賣價差 proxy、低流動性排除。

## 4. 建議模型架構

下一階段建議把 WallWin Gem 改為七大分數：

| 分數 | 用途 | 權重建議 |
| --- | --- | --- |
| Value Score | 是否估值合理 | 15% |
| Growth Score | 成長是否持續 | 15% |
| Quality Score | 公司體質是否可靠 | 20% |
| Momentum Score | 是否有趨勢與突破 | 20% |
| Risk Score | 波動、流動性、下行風險 | 15% |
| Regime Score | 大盤/產業環境 | 10% |
| HITL Score | 使用者私房資料校準 | 5% |

並輸出：

- 白馬勝率分數
- 黑馬勝率分數
- 綜合投審等級
- 否決條件清單
- 部位 sizing 建議
- 進出場與失效條件

## 5. 立即可執行的優化路線

第一階段：

- 擴充 `calculate_quant_matrix()`，加入 Quality / Growth / Liquidity / Relative Strength。
- 把 `technical_score` 改為 multi-factor score。
- Watchlist 增加多因子排序。

第二階段：

- 白馬/黑馬分別建立獨立分數模型。
- 加入大盤 regime，例如台股加權指數或 SPY/QQQ 作為市場濾網。
- 加入週線資料確認。

第三階段：

- 回測支援多策略比較。
- 加入參數最佳化與 walk-forward validation。
- 加入策略報告績效摘要。

## 6. 審查建議

建議你核准下一階段執行：

「多因子投審引擎升級：Quality / Growth / Relative Strength / Liquidity / Regime」

這會讓 WallWin Gem 從目前的單檔量化工具，升級成更接近投審會使用的股票勝率評估系統。

## 7. 參考方法論來源

- SEC Investor.gov 強調風險、資產配置、分散與再平衡的重要性。
- FINRA 投資人教育資料說明 stop / trailing stop 類型與風險，支持本次回測加入固定停損與移動停損。
- CFA Institute 因子投資文章指出常見股票因子包含 Value、Momentum、Quality、Low Volatility、Profitability 等，與本建議的多因子方向一致。
