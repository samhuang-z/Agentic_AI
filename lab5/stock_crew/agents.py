"""Shared CrewAI agents and LLM config used by both original and improved workflows."""

from __future__ import annotations

import os

from crewai import LLM, Agent
from dotenv import load_dotenv

from tools import get_fundamentals, get_price_history, get_recent_news

load_dotenv()


def build_llm() -> LLM:
    """Build the Anthropic Claude LLM used by every agent."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing — copy assignment2/.env into stock_crew/.env")
    return LLM(
        model="anthropic/claude-haiku-4-5-20251001",
        api_key=api_key,
        temperature=0.3,
    )


def build_agents(llm: LLM) -> dict[str, Agent]:
    """Construct the standard 5-agent crew used by the sequential workflow."""

    data_collector = Agent(
        role="Stock Data Collector",
        goal=(
            "Pull complete and up-to-date market, fundamental and news data for the requested ticker."
        ),
        backstory=(
            "You are a meticulous market data engineer. You always validate that the price, "
            "fundamental, and news payloads contain real values before declaring the data ready."
        ),
        tools=[get_price_history, get_fundamentals, get_recent_news],
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=5,
    )

    technical_analyst = Agent(
        role="Technical Analyst",
        goal=(
            "Evaluate the price action using SMA20/SMA50, RSI14, MACD and 6-month range to "
            "decide whether momentum is bullish, bearish or neutral."
        ),
        backstory=(
            "You trade with charts. You read trends, momentum and overbought/oversold signals "
            "and you express your confidence on a 1-10 scale."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=3,
    )

    fundamental_analyst = Agent(
        role="Fundamental Analyst",
        goal=(
            "Judge the quality of the business from PE, EPS growth, margins, ROE and analyst "
            "target price; flag whether valuation is cheap, fair or rich."
        ),
        backstory=(
            "You are a long-term equity analyst. You compare current multiples with historical "
            "and sector norms and you favour companies with growing earnings power."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=3,
    )

    risk_manager = Agent(
        role="Risk Manager",
        goal=(
            "Assess downside risk: volatility, drawdown vs. 6-month high, sector concentration, "
            "macro headlines. Output a risk level of LOW / MEDIUM / HIGH."
        ),
        backstory=(
            "You protect capital first. You distrust hype and always size positions based on "
            "the worst plausible outcome, not the best case."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=3,
    )

    report_writer = Agent(
        role="Investment Report Writer",
        goal=(
            "Produce a clear investment memo in Traditional Chinese with sections: 標的概況、"
            "技術面、基本面、風險、結論建議 (BUY / HOLD / SELL with confidence 1-10)."
        ),
        backstory=(
            "You translate analyst output into a one-page memo a portfolio manager can act on."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=3,
    )

    critic = Agent(
        role="Report Critic",
        goal=(
            "Score the investment memo from 1 to 10 on completeness, evidence, and clarity. "
            "Return STRICT JSON only: {\"score\": <int>, \"issues\": [<str>], \"verdict\": "
            "\"approve\"|\"revise\"}. Approve only when score >= 7 AND every required section "
            "(標的概況, 技術面, 基本面, 風險, 結論建議) is present with concrete numbers."
        ),
        backstory=(
            "You are a senior portfolio manager who rejects vague memos. You demand explicit "
            "numbers (price, RSI, PE, target) and a clear BUY/HOLD/SELL call."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
        max_iter=2,
    )

    return {
        "data_collector": data_collector,
        "technical_analyst": technical_analyst,
        "fundamental_analyst": fundamental_analyst,
        "risk_manager": risk_manager,
        "report_writer": report_writer,
        "critic": critic,
    }
