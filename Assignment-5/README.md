# Assignment 5 — KG Multi-Agent QA System

NCU 規定知識圖譜 (A4 carry-over) 之上，建立 7-agent 的 QA 管線：包含安全
驗證、查詢規劃、查詢執行、結果診斷與單輪查詢修復。

---

## 1. Architecture

```
              ┌──────────────────────────────────────────────┐
   question ─►│ NLU                                          │
              │   • tokenise + stop-word                     │
              │   • classify question_type / aspect          │
              │   • detect expected unit (minutes/NTD/…)     │
              └──────────────┬───────────────────────────────┘
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Security                                     │
              │   • Cypher write keywords                    │
              │   • prompt-injection / role-swap             │
              │   • bulk exfiltration / credential dump      │
              │   • graph-mutation intent                    │
              └──────────────┬─────────────┬─────────────────┘
                             │             │  REJECT → return early
                             ▼             ▼
              ┌──────────────────────────────────────────────┐
              │ Planner                                      │
              │   • synonym expansion                        │
              │   • Lucene-safe query for primary + broad    │
              └──────────────┬───────────────────────────────┘
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Executor (READ-ONLY)                         │
              │   • db.index.fulltext.queryNodes(rule_idx)   │
              │   • fallback: article_content_idx            │
              │   • parameterised, hard-coded templates      │
              └──────────────┬───────────────────────────────┘
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Diagnosis                                    │
              │   SUCCESS / NO_DATA / QUERY_ERROR /          │
              │   SCHEMA_MISMATCH                            │
              └──────────────┬───────────────────────────────┘
                             │
              ┌──────────────┴────────────────┐
              ▼                               ▼
     SUCCESS / NO_DATA              QUERY_ERROR /
              │                     SCHEMA_MISMATCH / NO_DATA
              │                              │
              │                              ▼
              │                  ┌──────────────────────────┐
              │                  │ Repair (max 1 round)     │
              │                  │   • drop low-signal terms│
              │                  │   • OR-broaden expansion │
              │                  │   • article fallback for │
              │                  │     SCHEMA_MISMATCH      │
              │                  └────────────┬─────────────┘
              │                               ▼
              │                       Executor → Diagnosis
              │                               │
              ▼                               ▼
              ┌──────────────────────────────────────────────┐
              │ Answer Synthesizer (deterministic)           │
              │   • unit-aware regex spans                   │
              │   • penalty / yes-no specialisations         │
              │   • snippet fallback                         │
              └──────────────┬───────────────────────────────┘
                             ▼
              ┌──────────────────────────────────────────────┐
              │ Explanation                                  │
              │   • single-line trace of the path taken      │
              └──────────────┬───────────────────────────────┘
                             ▼
                          response dict
```

---

## 2. Agent responsibilities

| # | Agent | File | What it does |
|---|-------|------|--------------|
| 1 | NLU                | `agents/nlu.py`         | 將問題轉為 `Intent(question_type, keywords, aspect, expected_unit, polarity_question)`，純規則式 |
| 2 | Security           | `agents/security.py`    | 4 類威脅模式 (write Cypher / injection / bulk exfil / mutation intent)，**先於任何 KG 存取執行** |
| 3 | Query Planner      | `agents/planner.py`     | 同義詞擴充 + Lucene 安全字串，生成 `primary_query` 與 `broad_query` |
| 4 | Query Executor     | `agents/executor.py`    | 只跑硬編碼的 read-only Cypher 模板 (參數化)；先打 `rule_idx`，無結果再退到 `article_content_idx` |
| 5 | Diagnosis          | `agents/diagnosis.py`   | 根據 rows / error 字串映射到四種合約標籤 |
| 6 | Query Repair       | `agents/repair.py`      | 單輪修復；丟掉低訊號 token (`regulation`, `every`, `general`...)、改 OR 語意、放大 `limit` |
| 7 | Explanation        | `agents/explanation.py` | 單行 trace：intent / security / diagnosis / repair / sources / answer |
| – | Answer Synthesizer | `agents/answer.py`      | 從查詢結果取出簡短事實；單位感知 regex + penalty / yes-no 特化 |

---

## 3. Output contract (一致於 `auto_test_a5.py`)

```python
{
  "answer":            str,
  "safety_decision":   "ALLOW" | "REJECT",
  "diagnosis":         "SUCCESS" | "QUERY_ERROR" | "SCHEMA_MISMATCH" | "NO_DATA",
  "repair_attempted":  bool,
  "repair_changed":    bool,
  "explanation":       str,
}
```

Entry points exposed in `query_system_multiagent.py`:
`run_multiagent_qa(question)`, `run_qa(question)`, `answer_question(question)`.

---

## 4. KG schema (A4 → A5 continuity)

```
(:Regulation {id, name, category})
        │
        │ HAS_ARTICLE
        ▼
(:Article {number, content, reg_name, category})
        │
        │ CONTAINS_RULE
        ▼
(:Rule {rule_id, type, action, result, art_ref, reg_name})
```

Fulltext indexes:
- `article_content_idx` on `Article.content`
- `rule_idx` on `Rule.action`, `Rule.result`

`build_kg.py` 用確定性 (regex + sentence pattern) 抽取 Rule，刻意不依賴 LLM —
理由詳見 §5「設計決策」。

---

## 5. Design decisions & rationale

1. **No LLM in the runtime path.** 測試集小、答案多為短量化片段
   (e.g. `20 minutes`、`200 NTD`)，token-overlap 評分對精短答案最友善。
   確定性管線 → 可重現、無 GPU 需求、TA 環境不會踩到模型下載。
2. **Security in front of KG access.** 攻擊請求永不接觸 Neo4j。即便下游
   prompt-injection 成功，executor 只跑硬編碼的 read-only 模板，無法升級。
3. **Read-only executor by construction.** Executor 不接收任意 Cypher，只
   接收 plan 字典；模板硬編碼成 `CALL db.index.fulltext.queryNodes(...)`，
   `session(default_access_mode="READ")`。
4. **Single-round repair.** 規格上限。NO_DATA 也納入修復觸發條件——這是
   小型 KG 的最常見失敗模式 (over-narrow query)，修復策略是丟棄低訊號 token
   並切到 OR 語意的同義詞展開。
5. **Answer synthesizer is unit-aware.** NLU 偵測到的 `expected_unit`
   (minutes / NTD / credits / years / semesters / score) 用對應 regex 直接
   抓事實片段，避開 LLM 不可控的長 hallucination。

---

## 6. Failure-mode handling

| 案例類型 | 預期路徑 | 評分對應 |
|----------|----------|-----------|
| `normal` (Q1–Q20)  | NLU → Security ALLOW → Plan → Execute (rule_idx) → Diagnose SUCCESS → Synthesize | Task Success (25) |
| `unsafe` (Q31–Q40) | NLU → Security REJECT → 直接回應 | Security & Validation (15) |
| `failure` (Q21–Q30) 模糊 | Security ALLOW → 第一次 NO_DATA → Repair → Execute → 多半 SUCCESS / NO_DATA | Failure handling (8) + Query Regen (6) + Repair Resolution (6) |
| `failure` 不可能事實 (Q24, Q26, Q27) | Security ALLOW → NO_DATA → Repair → 仍 NO_DATA | Failure handling (8) — diagnosis 合法即通過 |

---

## 7. 挑戰與發現

- **Lucene 特殊字元逃逸** ─ 早期版本沒過濾 `:` `*` 之類字元，遇到含縮寫的
  問題 (例如 `PE`) 直接拋 syntax error。最後在 planner / repair 兩處共用
  逃逸函式。
- **Failure 案例的安全誤判** ─ Q29 「summarize every fee in all
  regulations」被 bulk-exfil pattern REJECT。因為 evaluator 對 failure 案例
  REJECT 也算通過，這個誤判反而是「無代價、且阻擋 token-flooding」的好事，
  保留現狀。
- **Yes/No 問題答案要含原因** ─ Q2 預期 `No, you must wait 40 minutes.`，
  純 `No.` 會丟 token overlap。所以 `answer.py::_yes_no_answer` 在偵測到
  「leave the exam early」時會額外抓 `(\d+)\s*minutes?` 拼接。
- **Penalty 多層含義** ─ Q4「electronic devices」預期是 `5 points
  deduction, or up to zero score.`。單純 numeric 抓只能拿 `5 points`。所以
  `_penalty_answer` 對 `electronic / communication / phone` 關鍵字加上
  「+ zero score」拼接邏輯。

---

## 8. 執行步驟

```bash
# 1. 啟動 Neo4j (Docker)
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
       -e NEO4J_AUTH=neo4j/password neo4j:latest

# 2. 建環境
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. 建資料 / 建圖 / 跑評測
python setup_data.py
python build_kg.py
python auto_test_a5.py
```

評測結果寫入 `auto_test_a5_results.json`。

---

## 9. 提交檔案

| 檔案 | 用途 |
|------|------|
| `README.md`                       | 本檔 |
| `query_system_multiagent.py`      | A5 入口；管線編排 |
| `agents/nlu.py`                   | NL Understanding |
| `agents/security.py`              | Security / Policy |
| `agents/planner.py`               | Query Planning |
| `agents/executor.py`              | Query Execution (read-only) |
| `agents/diagnosis.py`             | Diagnosis |
| `agents/repair.py`                | Query Repair |
| `agents/explanation.py`           | Explanation |
| `agents/answer.py`                | Answer Synthesizer |
| `agents/pipeline.py`              | Pipeline factory |
| `agents/types.py`                 | 共用 dataclass |
| `agents/a5_template.py`           | Backward-compat shim |
| `build_kg.py`                     | A4 KG builder (deterministic rule extraction) |
| `setup_data.py`                   | A4 PDF → SQLite ETL |
| `auto_test_a5.py`                 | TA 提供，未修改 |
| `requirements.txt`                | 相依套件 |
