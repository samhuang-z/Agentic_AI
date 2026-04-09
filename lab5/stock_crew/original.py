"""Original sequential workflow:

Data Collector -> Technical Analyst -> Fundamental Analyst -> Risk Manager -> Report Writer

No feedback, no branching. Run with:
    uv run python original.py NVDA
    uv run python original.py 2330.TW
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from crewai import Crew, Process, Task

from agents import build_agents, build_llm

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def build_tasks(symbol: str, agents: dict) -> list[Task]:
    collect = Task(
        description=(
            f"Collect price history, fundamentals and recent news for ticker {symbol}. "
            f"Use ALL three tools and return a consolidated JSON-like brief with every metric "
            f"you obtained. If any tool returns an error, mention it explicitly."
        ),
        expected_output=(
            "A structured brief that lists last_close, sma20, sma50, rsi14, macd, "
            "annualized_volatility_pct, market_cap, trailing_pe, eps, growth, and 3 news headlines."
        ),
        agent=agents["data_collector"],
    )

    technical = Task(
        description=(
            f"Using ONLY the data brief produced earlier, write a technical-analysis paragraph "
            f"for {symbol}. Reference SMA20 vs SMA50 cross, RSI14 zone, MACD histogram sign, "
            f"and 30-day price change. End with a momentum verdict: bullish / neutral / bearish, "
            f"plus a confidence score 1-10."
        ),
        expected_output="One paragraph with explicit numbers and a final verdict line.",
        agent=agents["technical_analyst"],
        context=[collect],
    )

    fundamental = Task(
        description=(
            f"Using the same data brief, write a fundamental-analysis paragraph for {symbol}. "
            f"Mention trailing PE, forward PE, EPS growth, profit margin, ROE, debt/equity, "
            f"and analyst target. End with a valuation verdict: cheap / fair / rich, plus a "
            f"confidence score 1-10."
        ),
        expected_output="One paragraph with explicit numbers and a final verdict line.",
        agent=agents["fundamental_analyst"],
        context=[collect],
    )

    risk = Task(
        description=(
            f"Combine the technical and fundamental output and the news headlines to assess "
            f"the risk of holding {symbol} for the next 1-3 months. Reference annualized "
            f"volatility, drawdown vs. 6-month high, and any negative news. End with a risk "
            f"label: LOW / MEDIUM / HIGH."
        ),
        expected_output="One paragraph plus the risk label.",
        agent=agents["risk_manager"],
        context=[collect, technical, fundamental],
    )

    write = Task(
        description=(
            f"Write the final investment memo for {symbol} in Traditional Chinese. Required "
            f"sections (use these exact headers): 標的概況, 技術面, 基本面, 風險, 結論建議. "
            f"In 結論建議 give BUY / HOLD / SELL with a 1-10 confidence score and a one-line "
            f"reason. Cite concrete numbers (price, RSI, PE, target) — no vague language."
        ),
        expected_output="A markdown memo with all five required sections.",
        agent=agents["report_writer"],
        context=[collect, technical, fundamental, risk],
    )

    return [collect, technical, fundamental, risk, write]


def run(symbol: str) -> str:
    llm = build_llm()
    agents = build_agents(llm)
    tasks = build_tasks(symbol, agents)

    crew = Crew(
        agents=[
            agents["data_collector"],
            agents["technical_analyst"],
            agents["fundamental_analyst"],
            agents["risk_manager"],
            agents["report_writer"],
        ],
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff(inputs={"symbol": symbol})
    final_text = str(result)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = symbol.replace(".", "_")
    out_path = OUTPUT_DIR / f"original_{safe_symbol}_{timestamp}.md"
    out_path.write_text(
        f"# Original Workflow — {symbol}\n\n"
        f"_Run at {timestamp}_\n\n"
        f"---\n\n{final_text}\n",
        encoding="utf-8",
    )
    print(f"\n[saved] {out_path}")
    return final_text


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    run(symbol)
