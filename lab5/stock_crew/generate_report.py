"""Generate the lab5 PDF report from actual workflow outputs.

Reads the latest original_*.md and improved_*.md files in outputs/, builds an
8-section markdown report following the assignment template, then renders to
PDF via WeasyPrint with PingFang CJK font.

Run:
    uv run python generate_report.py
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import markdown
from dotenv import load_dotenv
from weasyprint import CSS, HTML

load_dotenv()

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "outputs"

# Student ID is read from .env (which is gitignored) so it never lands in the repo.
# Set STUDENT_ID=xxxxxxxxx in .env before running.
STUDENT_ID = os.environ.get("STUDENT_ID", "STUDENT_ID")
REPORT_PDF = ROOT / f"lab5_{STUDENT_ID}_report.pdf"


def latest(prefix: str) -> Path:
    files = sorted(OUT_DIR.glob(f"{prefix}*.md"))
    if not files:
        raise FileNotFoundError(f"no file matching {prefix}* in {OUT_DIR}")
    return files[-1]


def read_section(path: Path, after_marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    if after_marker in text:
        text = text.split(after_marker, 1)[1]
    return text.strip()


def extract_critic_history(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"## Critic history\s*\n+(.*?)\n+---", text, re.DOTALL)
    return m.group(1).strip() if m else "(no critic history found)"


def extract_conclusion(memo: str) -> str:
    """Pull the 結論建議 section out of a memo for before/after comparison."""
    m = re.search(r"##\s*結論建議.*?(?=\n##\s|\Z)", memo, re.DOTALL)
    return m.group(0).strip() if m else "(no 結論建議 section found)"


def render_memo_block(memo_md: str, label: str, css_class: str) -> str:
    """Render a memo snippet (raw markdown) as inline HTML inside a styled box.

    Demote any ## headings to h5 so they do not collide with the report's own h2.
    Returns an HTML string that markdown extras will pass through unchanged.
    """
    demoted = re.sub(r"^##\s+", "##### ", memo_md, flags=re.MULTILINE)
    demoted = re.sub(r"^#\s+", "##### ", demoted, flags=re.MULTILINE)
    inner_html = markdown.markdown(
        demoted,
        extensions=["extra", "tables", "sane_lists"],
    )
    return (
        f'<div class="memo-box {css_class}">'
        f'<div class="memo-label">{label}</div>'
        f'{inner_html}'
        f'</div>'
    )


def build_markdown() -> str:
    orig_nvda = latest("original_NVDA")
    orig_2330 = latest("original_2330_TW")
    impr_nvda = latest("improved_NVDA")
    impr_2330 = latest("improved_2330_TW")

    nvda_critic = extract_critic_history(impr_nvda)
    tw_critic = extract_critic_history(impr_2330)

    nvda_orig_concl = extract_conclusion(read_section(orig_nvda, "---"))
    nvda_impr_concl = extract_conclusion(read_section(impr_nvda, "## Final memo"))
    tw_orig_concl = extract_conclusion(read_section(orig_2330, "---"))
    tw_impr_concl = extract_conclusion(read_section(impr_2330, "## Final memo"))

    nvda_before_html = render_memo_block(nvda_orig_concl, "Before — Original Workflow", "before")
    nvda_after_html = render_memo_block(nvda_impr_concl, "After — Improved Workflow", "after")

    today = datetime.now().strftime("%Y-%m-%d")

    md = f"""
# NCU Agentic AI — Lab 5: CrewAI 多代理人股票分析

**學號：** {STUDENT_ID}　　**日期：** {today}　　**框架：** CrewAI + Anthropic Claude Haiku 4.5

---

## 1. Topic & Objectives

**My topic：** 多代理人股票投資分析助手（Multi-Agent Stock Investment Analyst）

**What I expect the AI team to deliver：** 給定一支股票代號（例如 `NVDA` 或 `2330.TW`），AI 團隊應該自動從 yfinance 抓取價格、技術指標、財報與新聞，分別從技術面、基本面、風險面分析後，產出一份具體可交易的投資備忘錄。備忘錄必須包含明確的 BUY / HOLD / SELL 建議，以及五個可執行的交易參數：**進場價、止損價、目標價、持有期、部位建議**——而不是模糊的「考慮買進」或「適當配置」。

本次實驗的核心目標不只是「跑通 multi-agent 流程」，而是觀察 **單純加 agent 是否真能改善輸出品質**，並嘗試以 *workflow design* 取代 *agent count* 來解決問題。

---

## 2. Agent Design

| # | Agent | Role | Responsibilities | Tools |
|---|---|---|---|---|
| 1 | **Data Collector** | 市場資料工程師 | 用 yfinance 抓股價、技術指標、財報、新聞，輸出結構化 brief | `get_price_history`, `get_fundamentals`, `get_recent_news` |
| 2 | **Technical Analyst** | 技術分析師 | 解讀 SMA20/50、RSI14、MACD、波動率，給多空結論 + 信心度 | – |
| 3 | **Fundamental Analyst** | 基本面分析師 | 解讀 PE、EPS、ROE、營收成長、目標價，給估值結論 | – |
| 4 | **Risk Manager** | 風控專員 | 評估波動率、回檔幅度、新聞風險，給 LOW/MED/HIGH 等級 | – |
| 5 | **Report Writer** | 投資備忘錄撰寫 | 整合三方分析，產出含五大段落的繁中報告 | – |
| 6 | **Critic** *(改進後新增)* | 嚴格的 PM 審稿員 | 對 Writer 產出評分 1-10，檢查五個 tradable elements 是否齊全，回傳 JSON | – |

LLM 統一使用 `anthropic/claude-haiku-4-5-20251001`（temperature=0.3），符合課程 API 配額。

---

## 3. Original Workflow (Sequential)

<div class="flow-chain">
  <span class="node">Data Collector</span><span class="arrow">→</span>
  <span class="node">Technical Analyst</span><span class="arrow">→</span>
  <span class="node">Fundamental Analyst</span><span class="arrow">→</span>
  <span class="node">Risk Manager</span><span class="arrow">→</span>
  <span class="node">Report Writer</span><span class="arrow">→</span>
  <span class="node output">Output</span>
</div>

**Brief description：** 五個 agent 完全 sequential，CrewAI 用 `Process.sequential` 串接，每個 task 透過 `context=[...]` 取得前面的輸出。Data Collector 先抓資料，三位分析師依序產生技術面、基本面、風險面段落，最後 Report Writer 把所有東西整合成繁中投資備忘錄。

實作位於 `original.py`。整個流程沒有任何回饋、沒有條件分支，也沒有重試——一條直線跑到底。

---

## 4. Workflow Improvements (Key Changes)

我做了 **兩個** 改進，分別屬於「條件分支」與「Agent feedback loop」兩種類型：

- ☑ **Conditional branching (if/else)** — 在 Data Collector 之後，加入 Python 端的 schema 驗證；若必要欄位缺失就重跑 collector，**且加上更嚴格的 prompt**。
- ☑ **Agent feedback loop** — 在 Report Writer 之後新增 Critic agent，以 JSON 評分。若 score &lt; 7 或缺少任何「五大可交易要素」，就把 critic 的 issues 回灌給 Writer 重寫，最多 2 次。

### Updated workflow

<div class="flow-steps">
<ol>
  <li><strong>Data Collector</strong> 用 yfinance 抓價格、財報、新聞</li>
  <li><strong>Schema Validator</strong>（Python 端）檢查必要欄位
    <ul><li class="branch">if 缺失 → 退回 step 1，加嚴 prompt 重抓（最多 1 次）</li></ul>
  </li>
  <li><strong>Technical Analyst</strong> 解讀技術指標</li>
  <li><strong>Fundamental Analyst</strong> 解讀基本面</li>
  <li><strong>Risk Manager</strong> 評估風險</li>
  <li><strong>Report Writer</strong> 撰寫繁中投資備忘錄</li>
  <li><strong>Critic</strong> 用 strict JSON 評分 1-10
    <ul>
      <li class="branch">if score &lt; 7 或缺五大要素 → 退回 step 6 重寫，附上 issues（最多 2 次）</li>
      <li class="branch">if score ≥ 7 → 進入 Output</li>
    </ul>
  </li>
  <li class="output-step"><strong>Output</strong> 最終備忘錄</li>
</ol>
</div>

實作位於 `improved.py`，loop 由 Python 端控制（不依賴 CrewAI 內建 hierarchical process），程式結構乾淨且容易 debug。Critic 的 prompt 強制它輸出 strict JSON：

```python
{{"score": <int>, "issues": [<str>], "verdict": "approve"|"revise"}}
```

並且明確要求備忘錄的「結論建議」必須包含五個 tradable elements：進場價、止損價、目標價、持有期、部位建議（單位 % of portfolio）。

---

## 5. Rationale

**Problems encountered：**

1. **Original workflow 的輸出表面看起來很好**——文字流暢、有引用數字、結構完整——但仔細檢查會發現 Writer 經常**在「結論建議」段落漏掉一兩個關鍵欄位**。例如 NVDA 的 original 輸出有止損價 $165、目標價提到分析師共識，但**部位建議只寫「考慮高波動率配置適當部位規模」沒有具體 %**，持有期也沒寫死。對 PM 而言這是不能執行的備忘錄。
2. **加更多 agent 並沒有解決這個問題**。我一開始想加一位「Position Sizer」agent，但這只會讓流程更長，而且 Writer 還是會繼續漏要素，因為 Writer 不知道下游檢查的標準。
3. **真正缺的是「驗收標準」**——沒有人告訴 Writer 「五個欄位必須齊全」，所以它每次的判斷都不一致。

**Therefore I changed the workflow to：** 把驗收標準從「軟性 prompt」變成「硬性 critic + JSON 評分 + revision loop」。Critic 的角色是執行 business rule，不是再生產內容；Writer 收到具體的 issues 後就有明確修正方向。

---

## 6. Effects of the Changes

### NVDA 實際對照（同一天、同樣資料）

**Critic history（improved 版本）：**

```
{nvda_critic}
```

第 0 次草稿被打 5 分退回，列出 6 條缺失，第 1 次重寫後拿 9 分通過。

{nvda_before_html}

{nvda_after_html}

可以看到 improved 版本在「結論建議」內多出了一張**完整的交易執行參數表**，五個欄位（進場價、目標價、止損價、持有期、部位建議）齊全且有具體數字——這正是 critic 第一輪退回時要求的。

### 2330.TW 對照

**Critic history：**

```
{tw_critic}
```

有趣的是，2330.TW 的 Writer 第一輪就拿到 score 9 直接通過，沒有觸發 revision。這說明 **feedback loop 的成本是「品質好時就只跑一次」，效益是「品質不好時自動修正」**——是不對稱的、值得的。

---

## 7. Observations (Key Takeaways)

I observed that Multi-Agent systems：

1. **加 agent 不等於加品質**。我原本以為「再加一位 Position Sizer」就能解決，但實作下來發現問題不在 *缺少 agent*，而在 *缺少驗收回饋*。CrewAI 範例 repo 強調的「careful workflow design matters more than adding agents」我是真的踩過才理解。
2. **Critic 的角色是「執行業務規則」而不是「再生產內容」**。把硬性檢查條件寫進 critic prompt（必須包含 X、Y、Z 五項），比寫進 Writer prompt 更有效——因為 Writer 同時要權衡很多東西，會自然「忘記」；而 Critic 只做一件事，不會妥協。
3. **Strict JSON 輸出 + Python 端解析**比依賴 CrewAI hierarchical process 更可控。我最初想用 CrewAI 內建的 hierarchical manager，但 manager 的決策過程是黑盒、不易測試。改用 Python loop 控制 retry 次數、檢查 verdict，整個流程透明且可單元測試。
4. **不對稱的 feedback loop 值得加**。對 2330.TW 這種一次過的案例，improved 版只多花一次 critic 呼叫的成本；對 NVDA 這種第一輪不過的案例，loop 自動修正而不需人工介入。這正是 multi-agent + workflow design 的價值。
5. **條件分支可以放在 Python 而不是 LLM 內**。Data Collector 的 schema 驗證用簡單的 string match 就夠了，不需要再讓 LLM 自評。把確定性檢查放在程式碼端，把不確定性決策放在 agent 端，是比較健康的分工。

---

## 8. Future Improvements

1. **多 critic / debate**：目前只有一位 Critic，可以引入第二位「保守派 Critic」與「積極派 Critic」對同一份備忘錄分別評分，讓 Writer 在兩邊意見之間迭代——這是 EMNLP 2024 *Multi-Agent Debate* 論文的核心想法。
2. **背測（backtesting）**：把過去 6 個月每週執行一次 improved workflow，比對它當時的 BUY/HOLD/SELL 建議和後續 30 天股價走勢，計算命中率與夏普比率。沒有這個，所有 agent 的建議都只是文字。
3. **更豐富的工具**：目前只有 yfinance。可以再加上 SEC EDGAR（10-K/10-Q）、FRED 總經數據、Twitter sentiment，讓 Data Collector 有更完整的素材。
4. **Position Sizer Agent（這次刻意不加）**：在 critic 證明 workflow design 已經能逼出五個欄位後，可以讓專門的 Position Sizer agent 用 Kelly Criterion 等量化方法產生 % of portfolio 數字，取代 Writer 的人工估算。
5. **整合 LangGraph**：把目前 Python 手動 loop 的部分改用 LangGraph 的 StateGraph，可以視覺化 workflow 並自動處理 retry / 並行。

---

## 附錄：專案結構

```
lab5/stock_crew/
├── pyproject.toml          # uv 管理依賴
├── .env                    # ANTHROPIC_API_KEY
├── tools.py                # yfinance 包成 CrewAI tool
├── agents.py               # 6 個 agent + LLM config
├── original.py             # Sequential workflow
├── improved.py             # Conditional branching + Critic loop
├── generate_report.py      # 本 PDF 產生器
└── outputs/                # 每次執行的 markdown 結果（含 critic history）
```

執行方式：

```bash
uv run python original.py NVDA
uv run python original.py 2330.TW
uv run python improved.py NVDA
uv run python improved.py 2330.TW
uv run python generate_report.py
```
"""
    return md.strip()


def md_to_html(md_text: str) -> str:
    body = markdown.markdown(
        md_text,
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8"><title>Lab5 CrewAI Report</title></head>
<body>{body}</body></html>"""


CSS_TEMPLATE = """
@page {
    size: A4;
    margin: 18mm 18mm 22mm 18mm;
    @bottom-center {
        content: "NCU Agentic AI Lab 5 — __STUDENT_ID__ — page " counter(page) " / " counter(pages);
        font-family: "Helvetica Neue", "Helvetica", "Heiti TC", sans-serif;
        font-size: 9pt;
        color: #888;
    }
}
body {
    font-family: "Helvetica Neue", "Helvetica", "Arial", "Heiti TC", "Heiti SC", "STHeiti", sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
}
h1 { font-size: 18pt; color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 6px; }
h2 { font-size: 14pt; color: #1a3a6c; margin-top: 22px; border-bottom: 1px solid #ccc; padding-bottom: 3px; }
h3 { font-size: 12pt; color: #2a4a7c; margin-top: 16px; }
h4 { font-size: 11pt; color: #2a4a7c; }
p { margin: 6px 0; }
strong { color: #1a1a1a; }
ul, ol { margin: 6px 0 6px 20px; }
li { margin-bottom: 3px; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 9.5pt;
}
th, td {
    border: 1px solid #ccc;
    padding: 5px 8px;
    text-align: left;
    vertical-align: top;
}
th { background: #f1f4f9; font-weight: bold; }
code {
    font-family: "Menlo", "Monaco", "Courier New", "Heiti TC", monospace;
    background: #f5f5f5;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 9.5pt;
    color: #b14;
}
pre {
    background: #f5f5f5;
    border-left: 3px solid #1a3a6c;
    padding: 8px 12px;
    font-family: "Menlo", "Monaco", "Courier New", "Heiti TC", monospace;
    font-size: 8.5pt;
    line-height: 1.4;
    overflow-x: auto;
    white-space: pre-wrap;
    word-wrap: break-word;
    color: #222;
    page-break-inside: avoid;
}
pre code { background: transparent; padding: 0; color: inherit; }
hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
blockquote {
    border-left: 3px solid #ccc;
    margin: 8px 0;
    padding: 4px 12px;
    color: #555;
}

/* ---- Workflow chain (Original) ---- */
.flow-chain {
    margin: 14px 0 18px 0;
    padding: 10px 12px;
    background: #f7f9fc;
    border: 1px solid #d9e0ec;
    border-radius: 4px;
    text-align: center;
    font-size: 10pt;
    line-height: 1.9;
}
.flow-chain .node {
    display: inline-block;
    background: #ffffff;
    border: 1px solid #1a3a6c;
    color: #1a3a6c;
    padding: 3px 9px;
    margin: 2px 0;
    border-radius: 3px;
    font-weight: 600;
}
.flow-chain .node.output {
    background: #1a3a6c;
    color: #ffffff;
}
.flow-chain .arrow {
    display: inline-block;
    color: #1a3a6c;
    padding: 0 6px;
    font-weight: bold;
}

/* ---- Workflow steps (Improved) ---- */
.flow-steps {
    margin: 14px 0 18px 0;
    padding: 12px 14px;
    background: #f7f9fc;
    border: 1px solid #d9e0ec;
    border-radius: 4px;
}
.flow-steps ol {
    margin: 0 0 0 20px;
    padding: 0;
}
.flow-steps > ol > li {
    margin: 4px 0;
    padding-left: 4px;
}
.flow-steps li.branch {
    list-style: none;
    color: #b14;
    font-size: 9.5pt;
    background: #fff5f5;
    border-left: 3px solid #b14;
    padding: 2px 8px;
    margin: 3px 0;
    border-radius: 2px;
}
.flow-steps li.output-step {
    color: #1a3a6c;
    font-weight: 600;
    margin-top: 6px;
}

/* ---- Memo comparison boxes ---- */
.memo-box {
    margin: 12px 0 18px 0;
    padding: 10px 14px;
    border-radius: 4px;
    border: 1px solid #ccc;
    page-break-inside: avoid;
}
.memo-box.before {
    background: #fdf6f3;
    border-left: 4px solid #c97259;
}
.memo-box.after {
    background: #f3f9f4;
    border-left: 4px solid #4a8f5a;
}
.memo-box .memo-label {
    font-size: 9.5pt;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 6px;
    color: #555;
}
.memo-box.before .memo-label { color: #8a3a22; }
.memo-box.after .memo-label { color: #2c5e3a; }
.memo-box h5 {
    font-size: 10.5pt;
    margin: 8px 0 4px 0;
    color: #1a1a1a;
}
.memo-box p { margin: 4px 0; font-size: 10pt; }
.memo-box ul, .memo-box ol { margin: 4px 0 4px 18px; }
.memo-box table { font-size: 9pt; margin: 6px 0; }
.memo-box th, .memo-box td { padding: 4px 6px; }
"""


def main() -> None:
    md_text = build_markdown()
    md_path = ROOT / "lab5_report_source.md"
    md_path.write_text(md_text, encoding="utf-8")
    html_text = md_to_html(md_text)
    css_str = CSS_TEMPLATE.replace("__STUDENT_ID__", STUDENT_ID)
    HTML(string=html_text, base_url=str(ROOT)).write_pdf(
        REPORT_PDF,
        stylesheets=[CSS(string=css_str)],
    )
    print(f"[saved markdown] {md_path}")
    print(f"[saved pdf]      {REPORT_PDF}")


if __name__ == "__main__":
    main()
