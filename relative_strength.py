# relative_strength.py - V2 benchmark-relative performance checks.
import logging
import math

logger = logging.getLogger(__name__)


def _valid_number(value: float | int | None) -> float | None:
    """Return a finite float or None for invalid relative-strength inputs."""
    try:
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception as e:
        logger.warning(f"[RelativeStrength] Invalid numeric input: {e}")
        return None


def evaluate_relative_strength(
    data: dict,
    spy_return_20d: float | None,
    qqq_return_20d: float | None,
) -> dict:
    """Check whether a stock outperformed SPY or QQQ over the configured lookback."""
    try:
        ticker = data.get("ticker", "<unknown>")
        stock_return = _valid_number(data.get("return_20d"))
        spy_return = _valid_number(spy_return_20d)
        qqq_return = _valid_number(qqq_return_20d)

        if stock_return is None or spy_return is None or qqq_return is None:
            return {
                "passed": False,
                "score": 0,
                "reasons": [],
                "reject_reasons": ["relative strength data unavailable"],
            }

        reasons: list[str] = []
        if stock_return > spy_return:
            reasons.append("outperformed SPY")
        if stock_return > qqq_return:
            reasons.append("outperformed QQQ")

        passed = bool(reasons)
        if not passed:
            logger.info(
                f"[RelativeStrength] {ticker}: lagged SPY/QQQ "
                f"({stock_return:.2f}% vs {spy_return:.2f}%/{qqq_return:.2f}%)"
            )
        return {
            "passed": passed,
            "score": 15 if passed else 0,
            "reasons": reasons,
            "reject_reasons": [] if passed else ["did not outperform SPY or QQQ"],
        }
    except Exception as e:
        logger.error(f"[RelativeStrength] Evaluation failed: {e}", exc_info=True)
        return {
            "passed": False,
            "score": 0,
            "reasons": [],
            "reject_reasons": [f"relative strength evaluation failed: {type(e).__name__}"],
        }
