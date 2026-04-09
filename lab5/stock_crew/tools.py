"""Stock data tools backed by yfinance, exposed as CrewAI tools."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import yfinance as yf
from crewai.tools import tool


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        if pd.isna(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = -delta.clip(upper=0).rolling(period).mean()
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    return _safe_float(rsi.iloc[-1])


def _macd(series: pd.Series) -> dict[str, float | None]:
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return {
        "macd": _safe_float(macd_line.iloc[-1]),
        "signal": _safe_float(signal.iloc[-1]),
        "histogram": _safe_float(hist.iloc[-1]),
    }


@tool("Get Stock Price History")
def get_price_history(symbol: str) -> str:
    """Fetch 6-month OHLCV history and key technical indicators (SMA20/50, RSI, MACD).

    Args:
        symbol: Ticker symbol, e.g. 'NVDA' or '2330.TW'.
    """
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo").dropna()
    if hist.empty:
        return json.dumps({"error": f"no price data for {symbol}", "symbol": symbol})

    close = hist["Close"]
    last_close = _safe_float(close.iloc[-1])
    sma20 = _safe_float(close.rolling(20).mean().iloc[-1])
    sma50 = _safe_float(close.rolling(50).mean().iloc[-1])
    high_52w = _safe_float(close.max())
    low_52w = _safe_float(close.min())
    pct_30d = _safe_float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if len(close) > 21 else None
    volatility = _safe_float(close.pct_change().std() * (252**0.5) * 100)

    payload = {
        "symbol": symbol,
        "as_of": str(hist.index[-1].date()),
        "last_close": last_close,
        "sma20": sma20,
        "sma50": sma50,
        "high_6mo": high_52w,
        "low_6mo": low_52w,
        "pct_change_30d": pct_30d,
        "annualized_volatility_pct": volatility,
        "rsi14": _rsi(close),
        "macd": _macd(close),
    }
    return json.dumps(payload, ensure_ascii=False)


@tool("Get Stock Fundamentals")
def get_fundamentals(symbol: str) -> str:
    """Fetch fundamental data: company name, sector, PE, EPS, market cap, margins, growth.

    Args:
        symbol: Ticker symbol, e.g. 'NVDA' or '2330.TW'.
    """
    ticker = yf.Ticker(symbol)
    try:
        info = ticker.info or {}
    except Exception as exc:  # pragma: no cover - network jitter
        return json.dumps({"error": str(exc), "symbol": symbol})

    payload = {
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "eps_trailing": info.get("trailingEps"),
        "eps_forward": info.get("forwardEps"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "debt_to_equity": info.get("debtToEquity"),
        "return_on_equity": info.get("returnOnEquity"),
        "dividend_yield": info.get("dividendYield"),
        "recommendation": info.get("recommendationKey"),
        "target_mean_price": info.get("targetMeanPrice"),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


@tool("Get Recent Stock News")
def get_recent_news(symbol: str) -> str:
    """Fetch up to 5 recent news headlines for the symbol via yfinance.

    Args:
        symbol: Ticker symbol.
    """
    ticker = yf.Ticker(symbol)
    try:
        items = ticker.news or []
    except Exception as exc:  # pragma: no cover
        return json.dumps({"error": str(exc), "symbol": symbol, "news": []})

    headlines = []
    for item in items[:5]:
        content = item.get("content") if isinstance(item, dict) else None
        if content:
            headlines.append({
                "title": content.get("title"),
                "summary": (content.get("summary") or "")[:280],
                "publisher": (content.get("provider") or {}).get("displayName"),
                "pub_date": content.get("pubDate"),
            })
        elif isinstance(item, dict):
            headlines.append({
                "title": item.get("title"),
                "publisher": item.get("publisher"),
                "pub_date": item.get("providerPublishTime"),
            })
    return json.dumps({"symbol": symbol, "count": len(headlines), "news": headlines}, ensure_ascii=False)
