# signals.py — Bullish pullback signal detection logic.
import logging
import math

from config import (
    MAX_SIGNALS,
    PULLBACK_TOLERANCE,
    RSI_PULLBACK_MIN,
    RSI_PULLBACK_MAX,
    RSI_PULLBACK_MID,
    SL_BUFFER_PCT,
    TP2_RISK_MULTIPLE,
    TP3_RISK_MULTIPLE,
)

logger = logging.getLogger(__name__)


def _finite_values(*values: float) -> bool:
    """Return True only when every value is finite."""
    try:
        return all(math.isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False


def detect_signal(data: dict) -> str | None:
    """
    Return 'BULLISH' when the latest bar matches the pullback setup.

    Criteria:
    - EMA20 > EMA50 > EMA200
    - Low touches EMA20 or EMA50 within PULLBACK_TOLERANCE
    - Close > Open
    - RSI in [RSI_PULLBACK_MIN, RSI_PULLBACK_MAX]
    - Volume >= 20-day volume SMA
    """
    try:
        open_ = float(data["open"])
        close = float(data["close"])
        low = float(data["low"])
        ema20 = float(data["ema20"])
        ema50 = float(data["ema50"])
        ema200 = float(data["ema200"])
        rsi = float(data["rsi"])
        volume = float(data["volume"])
        vol_sma20 = float(data["vol_sma20"])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"[Signals] Invalid or missing data: {e}")
        return None

    if not _finite_values(open_, close, low, ema20, ema50, ema200, rsi, volume, vol_sma20):
        return None

    trend_ok = ema20 > ema50 > ema200
    pullback_ok = (
        low <= ema20 * (1 + PULLBACK_TOLERANCE)
        or low <= ema50 * (1 + PULLBACK_TOLERANCE)
    )
    candle_ok = close > open_
    rsi_ok = RSI_PULLBACK_MIN <= rsi <= RSI_PULLBACK_MAX
    volume_ok = volume >= vol_sma20

    if trend_ok and pullback_ok and candle_ok and rsi_ok and volume_ok:
        return "BULLISH"
    return None


def _with_risk_levels(data: dict) -> dict | None:
    """Attach swing-low stop loss and 2R/3R take-profit levels."""
    try:
        close = float(data["close"])
        swing_low = float(data["swing_low_5"])
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"[Signals] Missing risk-level data: {e}")
        return None

    if not _finite_values(close, swing_low):
        return None

    sl = swing_low * (1 - SL_BUFFER_PCT)
    risk = close - sl
    if risk <= 0:
        logger.warning(f"[Signals] {data.get('ticker', '<unknown>')}: non-positive risk")
        return None

    return {
        **data,
        "signal_type": "BULLISH",
        "sl": round(sl, 2),
        "tp2": round(close + risk * TP2_RISK_MULTIPLE, 2),
        "tp3": round(close + risk * TP3_RISK_MULTIPLE, 2),
    }


def filter_signals(screener_results: list[dict]) -> list[dict]:
    """
    Keep bullish pullback setups, attach risk levels, rank by RSI proximity
    to the pullback-band midpoint, and cap at MAX_SIGNALS.
    """
    bullish: list[dict] = []

    for data in screener_results:
        if detect_signal(data) != "BULLISH":
            continue
        enriched = _with_risk_levels(data)
        if enriched is not None:
            bullish.append(enriched)

    bullish.sort(key=lambda x: abs(x["rsi"] - RSI_PULLBACK_MID))
    capped = bullish[:MAX_SIGNALS]
    logger.info(
        f"[Signals] Found: {len(bullish)} bullish pullbacks → "
        f"sending {len(capped)} (cap={MAX_SIGNALS})"
    )
    return capped
