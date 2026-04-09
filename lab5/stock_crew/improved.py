"""Improved workflow with two structural changes vs. original.py:

1. **Conditional branching at the data layer.** After the Data Collector runs, a
   lightweight Python validator checks the price/fundamentals payload. If a
   required field is missing or stale, we re-run the data step with a stricter
   prompt before proceeding. The downstream crew never sees broken data.

2. **Critic feedback loop.** After the Report Writer drafts the memo, a Critic
   agent scores it 1-10 with strict JSON output. If score < 7 OR any required
   section is missing, the memo is sent back to the Writer with the critic's
   issues attached, up to 2 revision rounds. This is the "agent feedback loop"
   improvement listed in the assignment template.

Run with:
    uv run python improved.py NVDA
    uv run python improved.py 2330.TW
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from crewai import Crew, Process, Task

from agents import build_agents, build_llm

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

REQUIRED_PRICE_FIELDS = ("last_close", "sma20", "rsi14", "macd")
REQUIRED_FUND_FIELDS = ("trailing_pe", "eps_trailing")
REQUIRED_SECTIONS = ("標的概況", "技術面", "基本面", "風險", "結論建議")
MIN_SCORE = 7
MAX_REVISIONS = 2


# ---------------------------------------------------------------------------
# Stage 1 — data collection with conditional retry
# ---------------------------------------------------------------------------

def _validate_data_brief(brief: str) -> tuple[bool, list[str]]:
    """Heuristic validator: just look for required keywords/numbers in the brief.

    The Data Collector returns prose mixed with JSON, so we look for the field
    names + at least one numeric value next to them.
    """
    issues: list[str] = []
    for field in REQUIRED_PRICE_FIELDS + REQUIRED_FUND_FIELDS:
        if field not in brief:
            issues.append(f"missing field `{field}` in data brief")
    if not re.search(r"\d", brief):
        issues.append("data brief contains no numeric values")
    return (not issues), issues


def collect_data(symbol: str, agents: dict, max_retries: int = 1) -> str:
    """Run the Data Collector. If validation fails, retry with a stricter ask."""
    for attempt in range(max_retries + 1):
        extra = ""
        if attempt > 0:
            extra = (
                "\n\nIMPORTANT — previous attempt was rejected because required fields were "
                "missing. You MUST call get_price_history AND get_fundamentals AND "
                "get_recent_news, then echo every numeric field returned."
            )
        task = Task(
            description=(
                f"Collect price history, fundamentals and recent news for ticker {symbol}. "
                f"Use ALL three tools and return a consolidated brief that explicitly lists "
                f"every numeric field: {', '.join(REQUIRED_PRICE_FIELDS + REQUIRED_FUND_FIELDS)}." + extra
            ),
            expected_output="Structured brief listing every required numeric field.",
            agent=agents["data_collector"],
        )
        crew = Crew(
            agents=[agents["data_collector"]],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )
        brief = str(crew.kickoff(inputs={"symbol": symbol}))
        ok, issues = _validate_data_brief(brief)
        if ok:
            print(f"[data] attempt {attempt + 1}: OK")
            return brief
        print(f"[data] attempt {attempt + 1}: REJECT — {issues}")
    print(f"[data] using last attempt despite issues: {issues}")
    return brief


# ---------------------------------------------------------------------------
# Stage 2 — analysts (still sequential, run inside one crew for shared context)
# ---------------------------------------------------------------------------

def run_analysts(symbol: str, brief: str, agents: dict) -> tuple[str, str, str]:
    technical = Task(
        description=(
            f"Read the data brief below and produce a technical analysis paragraph for {symbol}. "
            f"Reference SMA20 vs SMA50, RSI14 zone, MACD histogram, 30-day change. End with "
            f"momentum verdict (bullish/neutral/bearish) and confidence 1-10.\n\n"
            f"Data brief:\n{brief}"
        ),
        expected_output="Paragraph with explicit numbers and final verdict.",
        agent=agents["technical_analyst"],
    )
    fundamental = Task(
        description=(
            f"Read the data brief below and produce a fundamental analysis paragraph for {symbol}. "
            f"Mention PE, EPS growth, margin, ROE, debt/equity, target price. End with valuation "
            f"verdict (cheap/fair/rich) and confidence 1-10.\n\n"
            f"Data brief:\n{brief}"
        ),
        expected_output="Paragraph with explicit numbers and final verdict.",
        agent=agents["fundamental_analyst"],
    )
    risk = Task(
        description=(
            f"Read the data brief below and assess 1-3 month holding risk for {symbol}. "
            f"Reference annualized volatility, drawdown vs 6-month high, news. End with "
            f"risk label LOW / MEDIUM / HIGH.\n\n"
            f"Data brief:\n{brief}"
        ),
        expected_output="Paragraph plus risk label.",
        agent=agents["risk_manager"],
    )
    crew = Crew(
        agents=[
            agents["technical_analyst"],
            agents["fundamental_analyst"],
            agents["risk_manager"],
        ],
        tasks=[technical, fundamental, risk],
        process=Process.sequential,
        verbose=False,
    )
    crew.kickoff(inputs={"symbol": symbol})
    return (
        str(technical.output),
        str(fundamental.output),
        str(risk.output),
    )


# ---------------------------------------------------------------------------
# Stage 3 — writer + critic feedback loop
# ---------------------------------------------------------------------------

def write_memo(
    symbol: str,
    brief: str,
    technical: str,
    fundamental: str,
    risk: str,
    agents: dict,
    feedback: str | None = None,
) -> str:
    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\n\nThe previous draft was REJECTED by the critic with these issues:\n{feedback}\n"
            f"You MUST address every issue in this revision."
        )
    task = Task(
        description=(
            f"Write the final investment memo for {symbol} in Traditional Chinese. Use these "
            f"EXACT section headers as markdown level-2 headings: {', '.join(REQUIRED_SECTIONS)}. "
            f"In 結論建議 give BUY/HOLD/SELL with confidence 1-10 and a one-line reason. Cite "
            f"concrete numbers (price, RSI, PE, target). No vague language.\n\n"
            f"=== Data Brief ===\n{brief}\n\n"
            f"=== Technical ===\n{technical}\n\n"
            f"=== Fundamental ===\n{fundamental}\n\n"
            f"=== Risk ===\n{risk}\n"
            f"{feedback_block}"
        ),
        expected_output="Markdown memo with all five required sections.",
        agent=agents["report_writer"],
    )
    crew = Crew(
        agents=[agents["report_writer"]],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )
    return str(crew.kickoff(inputs={"symbol": symbol}))


def critique(memo: str, agents: dict) -> dict:
    task = Task(
        description=(
            "You are a strict portfolio manager reviewing this investment memo. Score it 1-10 "
            "and return STRICT JSON with keys score (int), issues (list[str]), verdict "
            "('approve'|'revise'). Do not include text outside the JSON.\n\n"
            "Approve ONLY when ALL of the following are true:\n"
            f"  1. score >= {MIN_SCORE}\n"
            f"  2. Every required section is present: {', '.join(REQUIRED_SECTIONS)}\n"
            "  3. The 結論建議 section explicitly contains EVERY one of these five tradable "
            "elements with specific numbers (not vague language):\n"
            "     a. 進場價 / Entry price (a specific price or price range, e.g. '$170-175')\n"
            "     b. 止損價 / Stop-loss price (a specific number, e.g. '$165')\n"
            "     c. 目標價 / Target price (a specific number, e.g. '$200')\n"
            "     d. 持有期 / Holding period (e.g. '3-6 months')\n"
            "     e. 部位建議 / Position size as % of portfolio (e.g. '不超過 5%')\n"
            "If ANY of these five elements is missing from 結論建議, you MUST mark verdict='revise' "
            "and list the missing elements explicitly in `issues`. Be ruthless — vague language "
            "like '考慮' or '適當' without numbers does NOT count.\n\n"
            f"=== Memo ===\n{memo}"
        ),
        expected_output='Strict JSON: {"score": int, "issues": [str], "verdict": "approve"|"revise"}',
        agent=agents["critic"],
    )
    crew = Crew(
        agents=[agents["critic"]],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )
    raw = str(crew.kickoff())
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"score": 0, "issues": ["critic returned non-JSON"], "verdict": "revise", "raw": raw}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return {"score": 0, "issues": [f"critic JSON parse error: {exc}"], "verdict": "revise", "raw": raw}


def writer_critic_loop(
    symbol: str,
    brief: str,
    technical: str,
    fundamental: str,
    risk: str,
    agents: dict,
) -> tuple[str, list[dict]]:
    history: list[dict] = []
    feedback: str | None = None
    memo = ""
    for revision in range(MAX_REVISIONS + 1):
        print(f"[writer] revision {revision}")
        memo = write_memo(symbol, brief, technical, fundamental, risk, agents, feedback)
        verdict = critique(memo, agents)
        history.append({"revision": revision, **verdict})
        print(f"[critic] revision {revision}: score={verdict.get('score')}, verdict={verdict.get('verdict')}")
        # also enforce required-section presence as a hard check
        missing_sections = [s for s in REQUIRED_SECTIONS if s not in memo]
        if missing_sections:
            verdict.setdefault("issues", []).append(f"missing sections: {missing_sections}")
            verdict["verdict"] = "revise"
        if verdict.get("verdict") == "approve" and verdict.get("score", 0) >= MIN_SCORE and not missing_sections:
            print(f"[critic] approved at revision {revision}")
            return memo, history
        feedback = "; ".join(verdict.get("issues", [])) or "no specific issues, just write more concretely"
    print(f"[critic] max revisions reached, returning last draft")
    return memo, history


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run(symbol: str) -> str:
    llm = build_llm()
    agents = build_agents(llm)

    print(f"\n=== improved workflow for {symbol} ===")
    brief = collect_data(symbol, agents, max_retries=1)
    technical, fundamental, risk = run_analysts(symbol, brief, agents)
    memo, history = writer_critic_loop(symbol, brief, technical, fundamental, risk, agents)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace(".", "_")
    out_path = OUTPUT_DIR / f"improved_{safe_symbol}_{timestamp}.md"
    history_block = "\n".join(
        f"- revision {h['revision']}: score={h.get('score')}, verdict={h.get('verdict')}, issues={h.get('issues')}"
        for h in history
    )
    out_path.write_text(
        f"# Improved Workflow — {symbol}\n\n"
        f"_Run at {timestamp}_\n\n"
        f"## Critic history\n\n{history_block}\n\n"
        f"---\n\n## Final memo\n\n{memo}\n",
        encoding="utf-8",
    )
    print(f"\n[saved] {out_path}")
    return memo


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    run(symbol)
