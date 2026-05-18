# market_regime.py - V2 SPY/QQQ hard gate.
import logging
import math

logger = logging.getLogger(__name__)


def _as_float(row: dict, key: str) -> float:
    """Read a numeric market-regime field from a snapshot row."""
    try:
        value = float(row[key])
        if not math.isfinite(value):
            raise ValueError(f"{key} is not finite")
        return value
    except Exception as e:
        logger.warning(f"[MarketRegime] Invalid {key}: {e}")
        raise


def evaluate_market_regime(market_data: dict[str, dict]) -> dict:
    """
    Evaluate the V2 bullish market hard gate for SPY and QQQ.

    Returns a serializable dict with is_valid, score, summary, reasons, and
    invalid_reasons so the scheduler can stop before scanning stocks.
    """
    try:
        invalid_reasons: list[str] = []
        reasons: list[str] = []

        for symbol in ("SPY", "QQQ"):
            row = market_data.get(symbol)
            if not row:
                invalid_reasons.append(f"{symbol} market data unavailable")
                continue

            close = _as_float(row, "close")
            ema50 = _as_float(row, "ema50")
            ema200 = _as_float(row, "ema200")

            if close <= ema50:
                invalid_reasons.append(f"{symbol} close <= 50EMA")
            if close <= ema200:
                invalid_reasons.append(f"{symbol} close <= 200EMA")
            if ema50 <= ema200:
                invalid_reasons.append(f"{symbol} 50EMA <= 200EMA")
            if close > ema50 and close > ema200 and ema50 > ema200:
                reasons.append(f"{symbol} bullish EMA stack")

        is_valid = not invalid_reasons
        summary = "Bullish market regime" if is_valid else "Invalid market regime"
        logger.info(
            f"[MarketRegime] {summary}: "
            f"{'; '.join(invalid_reasons) if invalid_reasons else 'all hard gates passed'}"
        )
        return {
            "is_valid": is_valid,
            "score": 10 if is_valid else 0,
            "summary": summary,
            "reasons": reasons,
            "invalid_reasons": invalid_reasons,
        }
    except Exception as e:
        logger.error(f"[MarketRegime] Evaluation failed: {e}", exc_info=True)
        return {
            "is_valid": False,
            "score": 0,
            "summary": "Invalid market regime",
            "reasons": [],
            "invalid_reasons": [f"market regime evaluation failed: {type(e).__name__}"],
        }
