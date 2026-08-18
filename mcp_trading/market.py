"""Neutral market-data summaries for research context."""

from __future__ import annotations

from typing import Any

import yfinance as yf

from .data import validate_ticker


ALLOWED_PERIODS = {"5d", "1mo", "3mo", "6mo", "1y", "2y"}
ALLOWED_INTERVALS = {"1d", "1h", "30m", "15m"}


def _number(value: Any, digits: int = 4) -> float | None:
    try:
        if value != value:  # NaN
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _rsi(close, periods: int = 14) -> float | None:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / periods, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / periods, adjust=False).mean()
    denominator = loss.iloc[-1]
    if denominator == 0:
        return 100.0
    return _number(100 - (100 / (1 + gain.iloc[-1] / denominator)), 2)


def get_market_snapshot(
    symbol: str, period: str = "3mo", interval: str = "1d"
) -> dict[str, Any]:
    symbol = validate_ticker(symbol)
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"period는 {sorted(ALLOWED_PERIODS)} 중 하나여야 합니다.")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"interval은 {sorted(ALLOWED_INTERVALS)} 중 하나여야 합니다.")

    history = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    if history.empty or "Close" not in history:
        raise RuntimeError("해당 종목의 시장 데이터를 찾지 못했습니다.")

    close = history["Close"].dropna()
    if close.empty:
        raise RuntimeError("해당 종목의 종가 데이터가 비어 있습니다.")
    first = close.iloc[0]
    last = close.iloc[-1]
    change = ((last / first) - 1) * 100 if first else None
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

    return {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "bars": int(len(history)),
        "last_timestamp": str(history.index[-1]),
        "last_close": _number(last),
        "period_change_percent": _number(change, 2),
        "ema20": _number(ema20),
        "ema50": _number(ema50),
        "rsi14": _rsi(close),
        "period_high": _number(history["High"].max()) if "High" in history else None,
        "period_low": _number(history["Low"].min()) if "Low" in history else None,
        "latest_volume": (
            _number(history["Volume"].iloc[-1], 0) if "Volume" in history else None
        ),
        "note": "과거 시장 데이터 요약이며 매수·매도 지시나 수익 보장이 아닙니다.",
    }
