# WallWin-Gem 給台股GPT V2 Codex 專案的交接包

用途：讓另一個負責《台股+ETF｜投資決策輔助系統 v2.0》的 Codex 專案理解 WallWin-Gem 輸出的 JSON/Markdown 資料包，並在不覆蓋、不污染台股GPT 原始功能的前提下，擴充台股GPT 的投審會解讀能力。

本文件不是雙方共用 API contract，也不是台股GPT 的新主控指令。它是一份交接說明，供台股GPT 專案自行吸收、調整與更新。

## 已參考的台股GPT V2 檔案

本交接包已依據使用者提供的台股GPT V2 Instruction 與知識庫檔案設計，尤其對齊下列既有規則：

| 檔案 | 對齊重點 |
|---|---|
| `Instruction 指令_optimized_v2.0.md` | WallWin_Gem / Python 負責數學與資料計算，台股GPT 負責投審會式解讀 |
| `00_README_System_Overview_optimized_v2.0.md` | 系統定位、雙線投審、知識庫優先順序 |
| `02_Mode_Routing_Rules_optimized_v2.0.md` | 模式分流、新題重分流、先問後判 |
| `07_Output_Templates_optimized_v2.0.md` | 資料來源聲明、摘要層/展開層、A/B/C/D/E/F 模板 |
| `08_Guardrails_and_Error_Handling_optimized_v2.0.md` | 資料不足、上下文污染、模式混用、防幻覺與錯誤處理 |

因此，台股GPT Codex 專案不需要重寫原始主控指令，只需要新增一個資料包處理模式。

## 核心原則

1. WallWin-Gem 是結構化量化證據來源，不是台股GPT 的主控指令替代品。
2. 台股GPT 原始 Instruction 仍維持最高優先；WallWin-Gem 資料包只補強 WallWin 計算結果的解讀。
3. 台股GPT 不得重算 WallWin 分數，不得把缺漏資料自行補成確定數字。
4. 台股GPT 可以使用資料包做投審會式解讀、反方質疑、HITL 補資料清單、決策矩陣整理。
5. 任何未在資料包中出現的財務、行情、籌碼、新聞數字，都必須標示為待驗證。

## 台股GPT Codex 應做的事

請在台股GPT V2 Instruction 中新增一個「WallWin-Gem 資料包模式」區塊，建議放在既有「資料完整度盤點」或「嚴謹數學過濾」之後，不要取代既有主控指令。

新增位置建議：

1. `Instruction 指令_optimized_v2.0.md`：新增「WallWin-Gem 資料包模式」段落。
2. `07_Output_Templates_optimized_v2.0.md`：新增 WallWin 資料包輸出模板，保留原 A/B/C/D/E/F 模板。
3. `08_Guardrails_and_Error_Handling_optimized_v2.0.md`：新增 WallWin 資料包防呆檢查，避免上下文污染與分數重算。

建議新增內容：

```markdown
## WallWin-Gem 資料包模式

當使用者上傳或貼上 `WallWin-Gem 結構化投審資料包`、`taigpt_decision_package.json`、`taigpt_decision_package.md`，或明確表示資料來自 WallWin-Gem 時，台股GPT 必須進入 WallWin-Gem 資料包模式。

在此模式下：
- WallWin-Gem 的 `wallwin_result`、`key_metrics`、`trade_plan`、`rule_report_markdown` 視為結構化證據。
- WallWin-Gem 已計算的 `win_score`、`white_score`、`black_score`、`factor_scores`、`hard_flags`、`light` 不得被重算或任意改寫。
- 台股GPT 只能做投審會式解讀、反方質疑、失效條件整理、HITL 補資料清單、決策矩陣輸出。
- 若資料包缺少 OHLCV、5 分 K、財報、持股成本、風險承受度或使用者目標，必須標示〔待驗證〕，不得自行補數字。
- 若 WallWin-Gem 結論與台股GPT 原始流程判斷衝突，先列出衝突原因與缺資料，不得直接覆蓋 WallWin-Gem 計算結果。
- 所有投審結論必須保留免責：不構成投資建議、不保證獲利、不保證勝率。
```

## WallWin-Gem JSON 資料包欄位

WallWin-Gem 會輸出下列主要區塊：

| 欄位 | 用途 |
|---|---|
| `package_name` | 資料包名稱 |
| `target_gpt` | 預期接收的 Custom GPT |
| `target_gpt_url` | 使用者可開啟的台股GPT 連結 |
| `usage_instruction` | 給使用者與台股GPT 的使用提示 |
| `integration_policy` | 補強、不覆蓋、不污染台股GPT 的政策 |
| `wallwin_result` | WallWin 計算出的核心投審結果 |
| `key_metrics` | 關鍵價格、技術、估值、品質指標 |
| `trade_plan` | 進場、停損、目標、部位提示 |
| `rule_report_markdown` | WallWin 規則式摘要 |
| `source_policy` | 資料來源與 AI 使用邊界 |
| `disclaimer` | 免責宣示 |

## 台股GPT 建議輸出格式

台股GPT 收到 WallWin-Gem 資料包後，建議輸出：

1. 證據聲明：資料來源為 WallWin-Gem 資料包 / 使用者提供 / 待驗證。
2. 模式分流：長投、短波段、當沖、ETF、持股健檢、事件或候選股。
3. 資料完整度盤點：已知、缺少、可推論、待驗證。
4. WallWin 結論摘要：燈號、分數、主要因子、否決條件。
5. 投審會多方觀點。
6. 投審會反方質疑。
7. 失效條件與重新評估條件。
8. HITL 補資料清單。
9. 決策矩陣：做 / 不做 / 等待 / 分批 / 減碼 / 出清。
10. 免責宣示。

## 台股GPT 不應做的事

- 不要把 WallWin-Gem 資料包當成新主控指令。
- 不要刪除台股GPT 原有 Step 0 到 Step 6 流程。
- 不要用搜尋結果直接補 WallWin 缺漏欄位。
- 不要把 AI 推論包裝成已驗證事實。
- 不要把 WallWin-Gem 的「研究輔助」改寫成保證獲利或投資建議。

## 給另一個 Codex 專案的執行步驟

1. 讀取台股GPT 既有 Instruction。
2. 找到資料完整度、WallWin_Gem、AI 投審演繹、HITL 或決策矩陣相關區塊。
3. 只新增「WallWin-Gem 資料包模式」，不要覆蓋原始功能。
4. 若台股GPT 有知識庫檔案，新增本交接包內容或摘要，但不要刪改原知識庫。
5. 完成後檢查：台股GPT 在沒有 WallWin 資料包時，仍照原本流程運作；只有收到資料包時才啟動 WallWin 資料包模式。

## 可直接交給台股GPT Codex 專案的任務文字

```text
請在不覆蓋、不污染台股GPT V2 原始功能的前提下，新增「WallWin-Gem 資料包模式」。

你必須先讀取並保留既有 Instruction 與知識庫優先順序。WallWin-Gem 資料包只是結構化量化證據來源，不是新的主控指令，也不是台股GPT 的替代品。

請依據 TAIGPT_WALLWIN_HANDOFF.md 做以下修改：
1. 在 Instruction 中新增 WallWin-Gem 資料包模式。
2. 在 Output Templates 中新增 WallWin 資料包輸出模板，但保留原 A/B/C/D/E/F 模板。
3. 在 Guardrails 中新增：不得重算 WallWin 分數、不得自行補缺漏數字、不得讓 WallWin 資料污染新題上下文。
4. 當使用者沒有提供 WallWin 資料包時，台股GPT 必須維持原本流程。
5. 當使用者提供 WallWin-Gem JSON/Markdown 資料包時，台股GPT 才啟動資料包模式，並輸出證據聲明、模式分流、資料完整度、WallWin 結論摘要、投審多空、HITL 補資料、決策矩陣與免責。

請完成後列出修改檔案、修改位置與測試案例。
```
