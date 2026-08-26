"""Neutral market-data summaries for research context."""

from __future__ import annotations

from typing import Any

import yfinance as yf

from .data import validate_ticker


ALLOWED_PERIODS = {"5d", "1mo", "3mo", "6mo", "1y", "2y"}
ALLOWED_INTERVALS = {"1d", "1h", "30m", "15m"}
MIN_RECENT_BARS = 5
MAX_RECENT_BARS = 60


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
    latest_gain = gain.iloc[-1]
    denominator = loss.iloc[-1]
    if denominator == 0 and latest_gain == 0:
        return 50.0
    if denominator == 0:
        return 100.0
    return _number(100 - (100 / (1 + latest_gain / denominator)), 2)


def _load_history(symbol: str, period: str, interval: str):
    symbol = validate_ticker(symbol)
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"period는 {sorted(ALLOWED_PERIODS)} 중 하나여야 합니다.")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"interval은 {sorted(ALLOWED_INTERVALS)} 중 하나여야 합니다.")

    history = yf.Ticker(symbol).history(
        period=period,
        interval=interval,
        auto_adjust=True,
    )
    if history.empty or "Close" not in history:
        raise RuntimeError(f"{symbol}의 시장 데이터를 찾을 수 없습니다.")
    history = history.dropna(subset=["Close"])
    if history.empty:
        raise RuntimeError(f"{symbol}의 종가 데이터가 없습니다.")
    return symbol, history


def _trend_state(last: float, ema20: float, ema50: float) -> str:
    if last > ema20 > ema50:
        return "상승 정렬"
    if last < ema20 < ema50:
        return "하락 정렬"
    return "혼조 정렬"


def _momentum_state(rsi14: float | None, macd_histogram: float | None) -> str:
    if rsi14 is None or macd_histogram is None:
        return "계산 데이터 부족"
    if rsi14 >= 70:
        rsi_state = "RSI 고점권"
    elif rsi14 <= 30:
        rsi_state = "RSI 저점권"
    else:
        rsi_state = "RSI 중립권"
    macd_state = "MACD 양수" if macd_histogram >= 0 else "MACD 음수"
    return f"{rsi_state} · {macd_state}"


def _timestamp(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def get_market_snapshot(
    symbol: str, period: str = "3mo", interval: str = "1d"
) -> dict[str, Any]:
    symbol, history = _load_history(symbol, period, interval)
    close = history["Close"]
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


def get_chart_analysis_context(
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    recent_bars: int = 30,
) -> dict[str, Any]:
    """Build deterministic indicators to cross-check an attached chart image."""
    if isinstance(recent_bars, bool) or not isinstance(recent_bars, int):
        raise ValueError("recent_bars는 정수여야 합니다.")
    if not MIN_RECENT_BARS <= recent_bars <= MAX_RECENT_BARS:
        raise ValueError(
            f"recent_bars는 {MIN_RECENT_BARS}~{MAX_RECENT_BARS} 범위여야 합니다."
        )

    symbol, history = _load_history(symbol, period, interval)
    close = history["Close"]
    high = history["High"] if "High" in history else close
    low = history["Low"] if "Low" in history else close
    volume = history["Volume"] if "Volume" in history else None

    ema20_series = close.ewm(span=20, adjust=False).mean()
    ema50_series = close.ewm(span=50, adjust=False).mean()
    ema12_series = close.ewm(span=12, adjust=False).mean()
    ema26_series = close.ewm(span=26, adjust=False).mean()
    macd_series = ema12_series - ema26_series
    macd_signal_series = macd_series.ewm(span=9, adjust=False).mean()
    macd_histogram_series = macd_series - macd_signal_series

    sma20_series = close.rolling(20).mean()
    std20_series = close.rolling(20).std(ddof=0)
    bollinger_upper_series = sma20_series + (std20_series * 2)
    bollinger_lower_series = sma20_series - (std20_series * 2)

    previous_close = close.shift(1)
    true_range = (high - low).to_frame("range")
    true_range["high_gap"] = (high - previous_close).abs()
    true_range["low_gap"] = (low - previous_close).abs()
    atr14_series = true_range.max(axis=1).ewm(alpha=1 / 14, adjust=False).mean()

    last_close = float(close.iloc[-1])
    ema20 = float(ema20_series.iloc[-1])
    ema50 = float(ema50_series.iloc[-1])
    rsi14 = _rsi(close)
    macd = _number(macd_series.iloc[-1])
    macd_signal = _number(macd_signal_series.iloc[-1])
    macd_histogram = _number(macd_histogram_series.iloc[-1])

    reference_window = min(20, len(history))
    support_reference = low.tail(reference_window).min()
    resistance_reference = high.tail(reference_window).max()

    latest_volume = _number(volume.iloc[-1], 0) if volume is not None else None
    average_volume20 = (
        _number(volume.tail(20).mean(), 0) if volume is not None else None
    )
    volume_ratio = (
        _number(latest_volume / average_volume20, 2)
        if latest_volume is not None and average_volume20
        else None
    )

    bars: list[dict[str, Any]] = []
    for timestamp, row in history.tail(recent_bars).iterrows():
        bars.append(
            {
                "timestamp": _timestamp(timestamp),
                "open": _number(row.get("Open")),
                "high": _number(row.get("High")),
                "low": _number(row.get("Low")),
                "close": _number(row.get("Close")),
                "volume": _number(row.get("Volume"), 0),
            }
        )

    return {
        "symbol": symbol,
        "period": period,
        "interval": interval,
        "source": "Yahoo Finance via yfinance",
        "price_adjustment": "auto_adjusted",
        "data_timestamp": _timestamp(history.index[-1]),
        "bars_available": len(history),
        "indicator_warning": (
            None
            if len(history) >= 50
            else "50개 미만의 봉만 있어 장기 이동평균 해석 신뢰도가 낮습니다."
        ),
        "recent_bars": bars,
        "price": {
            "last_close": _number(last_close),
            "period_high": _number(high.max()),
            "period_low": _number(low.min()),
        },
        "trend": {
            "state": _trend_state(last_close, ema20, ema50),
            "ema20": _number(ema20),
            "ema50": _number(ema50),
            "sma20": _number(sma20_series.iloc[-1]),
            "sma50": _number(close.rolling(50).mean().iloc[-1]),
        },
        "momentum": {
            "state": _momentum_state(rsi14, macd_histogram),
            "rsi14": rsi14,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
        },
        "volatility": {
            "atr14": _number(atr14_series.iloc[-1]),
            "bollinger_middle20": _number(sma20_series.iloc[-1]),
            "bollinger_upper20": _number(bollinger_upper_series.iloc[-1]),
            "bollinger_lower20": _number(bollinger_lower_series.iloc[-1]),
        },
        "volume": {
            "latest": latest_volume,
            "average20": average_volume20,
            "latest_to_average20_ratio": volume_ratio,
        },
        "reference_levels": {
            "window_bars": reference_window,
            "recent_low_reference": _number(support_reference),
            "recent_high_reference": _number(resistance_reference),
            "note": "최근 봉의 단순 최저·최고 범위이며 확정 지지·저항선이 아닙니다.",
        },
        "usage_note": (
            "사용자가 첨부한 TradingView 차트의 종목·시간봉과 일치하는지 먼저 확인한 뒤 "
            "시각 분석을 교차 검증하는 참고 수치로만 사용하세요. MCP가 차트 이미지를 직접 "
            "가져오거나 보았다고 표현하면 안 됩니다. 매수·매도 지시나 수익 보장이 아닙니다."
        ),
    }
