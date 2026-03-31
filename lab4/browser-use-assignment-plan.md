# Plan: AI Browser Agent 作業

## 目標
用一個 AI 瀏覽器代理框架完成一個自動化任務，並撰寫報告。

## 步驟

### Phase 1: 環境建置
1. Clone PagePilot repo (`https://github.com/jason79461385/PagePilot`)
2. 建立 Python virtual environment，安裝所有依賴（requirements.txt）
3. 設定必要的 API key（OpenAI / Anthropic 等，看框架需求）
4. 確認 Playwright 或 Selenium 等瀏覽器驅動正確安裝（`playwright install`）

### Phase 2: 設計並執行一個自動化任務
1. 選一個明確的任務，例如：
   - 到某個電商網站搜尋商品並加入購物車
   - 到 Google Flights 搜尋航班
   - 到餐廳訂位網站完成預約流程
2. 撰寫對應的 agent 腳本來執行這個任務
3. 執行並記錄整個過程（截圖、log、成功/失敗點）
4. 如果失敗，記錄失敗在哪一步、原因是什麼

### Phase 3: 撰寫報告（Markdown 格式）

報告結構如下：

```markdown
# Activity: Browser Use - Report

## I. Implementation Overview
### Tool Selected
- 使用的框架名稱與版本

### Task Description
- 任務描述（做了什麼、目標網站是哪個）

### Execution Result
- 成功或失敗
- 如果失敗，卡在哪一步
- 附上關鍵截圖或 log

## II. Current Limitations of AI Browsers
分析以下四個面向（每個都要有具體觀察，不要空泛）：

### Latency
- 每一步推理+行動花了多久
- 整體完成任務的時間 vs 人類手動操作的時間

### Context Window
- 跨頁面時 agent 是否遺忘之前的資訊
- 在多步驟流程中表現如何

### DOM Perception
- 有沒有無法辨識的 UI 元素（dropdown、modal、iframe、shadow DOM）
- 對動態載入內容的處理能力

### Reliability
- agent 是否幻覺出不存在的按鈕/連結
- 是否重複執行相同動作陷入迴圈

## III. Challenges Encountered

### Environment Setup
- 安裝過程遇到的問題與解法

### Cost
- 大約消耗了多少 token / 花了多少錢
- 高解析度截圖對 token 的影響

### Security & CAPTCHA
- 是否遇到驗證碼、anti-bot 機制
- 如何處理或繞過（或無法繞過）
```

### Phase 4: 輸出
1. 將報告存成 `report.md`
2. 把執行過程的截圖放在 `screenshots/` 資料夾
3. 把 agent 腳本放在 `src/` 資料夾

## 資料夾結構
```
browser-use-assignment/
├── report.md
├── src/
│   └── agent_task.py    # 主要的 agent 腳本
├── screenshots/
│   └── ...              # 執行過程截圖
└── README.md            # 簡單說明如何執行
```
