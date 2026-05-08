# risk_engine.py - V2 trade plan and risk/reward calculations.
import logging
import math
from decimal import Decimal, ROUND_HALF_UP

from config import (
    V2_BUY_STOP_BUFFER_PCT,
    V2_HOLDING_STYLE,
    V2_STOP_BUFFER_PCT,
    V2_TARGET_1_R,
    V2_TARGET_2_R,
)

logger = logging.getLogger(__name__)


def _money(value: float) -> float:
    """Round money values using predictable half-up cents."""
    try:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception as e:
        logger.warning(f"[Risk] Money rounding failed: {e}")
        return round(float(value), 2)


def _value(data: dict, key: str) -> float | None:
    """Read a finite numeric risk input."""
    try:
        value = data.get(key)
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception as e:
        logger.warning(f"[Risk] {data.get('ticker', '<unknown>')}: invalid {key}: {e}")
        return None


def build_trade_plan(data: dict) -> dict | None:
    """Build V2 entry, stop, target, and placeholder sizing levels."""
    try:
        close = _value(data, "close")
        high = _value(data, "high")
        contraction_low = _value(data, "contraction_low")
        pivot_low = _value(data, "pivot_low")

        if close is None or high is None or contraction_low is None:
            return None

        stop_base = min(
            value for value in [contraction_low, pivot_low]
            if value is not None
        )
        stop_loss = _money(stop_base * (1 - V2_STOP_BUFFER_PCT))
        risk_per_share = _money(close - stop_loss)
        if risk_per_share <= 0:
            logger.warning(f"[Risk] {data.get('ticker', '<unknown>')}: non-positive risk")
            return None

        entry = _money(close)
        buy_stop = _money(high * (1 + V2_BUY_STOP_BUFFER_PCT))
        target_1 = _money(entry + risk_per_share * V2_TARGET_1_R)
        target_2 = _money(entry + risk_per_share * V2_TARGET_2_R)

        return {
            "entry": entry,
            "buy_stop": buy_stop,
            "stop_loss": stop_loss,
            "risk_per_share": risk_per_share,
            "target_1": target_1,
            "target_2": target_2,
            "expected_rr": V2_TARGET_1_R,
            "position_size": "Portfolio size required",
            "holding_style": V2_HOLDING_STYLE,
        }
    except Exception as e:
        logger.error(f"[Risk] Trade plan failed: {e}", exc_info=True)
        return None
