# risk_engine.py - V2 trade plan and risk/reward calculations.
import logging
import math
from decimal import Decimal, ROUND_HALF_UP

from config import (
    V3_ATR_STOP_MULTIPLE,
    V3_MIN_TACTICAL_STOP_DISTANCE_PCT,
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


def _distance_pct(entry: float, stop: float) -> float:
    """Return entry-to-stop distance as a ratio rounded for stable JSON/tests."""
    return round((entry - stop) / entry, 4)


def _candidate_result(
    *,
    source: str,
    stop: float | None,
    entry: float,
    structural_stop: float,
    structural_stop_distance_pct: float,
) -> dict:
    """Validate one possible tactical stop without raising into the scan."""
    result = {
        "stop": stop,
        "distance_pct": None,
        "valid": False,
        "reason": "",
    }
    if stop is None:
        result["reason"] = "missing candidate"
        return result

    stop = _money(stop)
    result["stop"] = stop
    if stop >= entry:
        result["reason"] = "candidate must be below entry"
        return result
    if stop <= structural_stop:
        result["reason"] = "candidate must be tighter than structural stop"
        return result

    distance_pct = _distance_pct(entry, stop)
    result["distance_pct"] = distance_pct
    if distance_pct < V3_MIN_TACTICAL_STOP_DISTANCE_PCT:
        result["reason"] = "candidate is too close to entry"
        return result
    if distance_pct > structural_stop_distance_pct:
        result["reason"] = "candidate is wider than structural stop"
        return result

    result["valid"] = True
    result["reason"] = "ok"
    return result


def _build_tactical_stops(
    *,
    data: dict,
    entry: float,
    structural_stop: float,
    structural_stop_distance_pct: float,
    contraction_low: float,
) -> tuple[float | None, str | None, float | None, dict]:
    """Build optional tactical stop metadata while leaving V2 stop_loss untouched."""
    swing_low_5 = _value(data, "swing_low_5")
    atr = _value(data, "atr")
    raw_candidates = {
        "contraction_low": contraction_low * (1 - V2_STOP_BUFFER_PCT),
        "recent_5d_low": (
            swing_low_5 * (1 - V2_STOP_BUFFER_PCT)
            if swing_low_5 is not None
            else None
        ),
        "atr": (
            entry - V3_ATR_STOP_MULTIPLE * atr
            if atr is not None
            else None
        ),
    }
    candidates = {
        source: _candidate_result(
            source=source,
            stop=stop,
            entry=entry,
            structural_stop=structural_stop,
            structural_stop_distance_pct=structural_stop_distance_pct,
        )
        for source, stop in raw_candidates.items()
    }
    for source in ["contraction_low", "recent_5d_low", "atr"]:
        candidate = candidates[source]
        if candidate["valid"]:
            return (
                candidate["stop"],
                source,
                candidate["distance_pct"],
                candidates,
            )
    return None, None, None, candidates


def build_trade_plan(data: dict) -> dict | None:
    """Build V2 entry, stop, target, and placeholder sizing levels."""
    try:
        close = _value(data, "close")
        high = _value(data, "high")
        contraction_low = _value(data, "contraction_low")
        pivot_low = _value(data, "pivot_low")

        if close is None or high is None or contraction_low is None:
            return None

        stop_options = [("contraction_low", contraction_low)]
        if pivot_low is not None:
            stop_options.append(("pivot_low", pivot_low))
        structural_stop_source, stop_base = min(stop_options, key=lambda item: item[1])
        stop_loss = _money(stop_base * (1 - V2_STOP_BUFFER_PCT))
        risk_per_share = _money(close - stop_loss)
        if risk_per_share <= 0:
            logger.warning(f"[Risk] {data.get('ticker', '<unknown>')}: non-positive risk")
            return None

        entry = _money(close)
        structural_stop_distance_pct = _distance_pct(entry, stop_loss)
        tactical_stop, tactical_stop_source, tactical_stop_distance_pct, tactical_stop_candidates = (
            _build_tactical_stops(
                data=data,
                entry=entry,
                structural_stop=stop_loss,
                structural_stop_distance_pct=structural_stop_distance_pct,
                contraction_low=contraction_low,
            )
        )
        buy_stop = _money(high * (1 + V2_BUY_STOP_BUFFER_PCT))
        target_1 = _money(entry + risk_per_share * V2_TARGET_1_R)
        target_2 = _money(entry + risk_per_share * V2_TARGET_2_R)

        # Resistance-aware R:R: cap the reward leg at the nearest overhead level
        # (52-week high or pivot) so expected_rr reflects realistic upside.
        resistance_options = []
        high_52w = _value(data, "high_52w")
        pivot = _value(data, "pivot")
        if high_52w is not None and high_52w > entry:
            resistance_options.append(("high_52w", high_52w))
        if pivot is not None and pivot > entry:
            resistance_options.append(("pivot", pivot))
        capped_target_1 = target_1
        rr_resistance_source = None
        if resistance_options:
            resistance_source, resistance = min(resistance_options, key=lambda item: item[1])
            effective_resistance = resistance * 0.98
            # Floor the cap at entry: if the buffer pulls resistance to/below
            # entry, there is no usable upside cap — fall back to target_1.
            if effective_resistance > entry:
                capped_target_1 = min(target_1, effective_resistance)
                if capped_target_1 != target_1:
                    rr_resistance_source = resistance_source
        actual_rr = round((capped_target_1 - entry) / risk_per_share, 2)

        return {
            "entry": entry,
            "buy_stop": buy_stop,
            "stop_loss": stop_loss,
            "structural_stop": stop_loss,
            "structural_stop_source": structural_stop_source,
            "structural_stop_distance_pct": structural_stop_distance_pct,
            "tactical_stop": tactical_stop,
            "tactical_stop_source": tactical_stop_source,
            "tactical_stop_distance_pct": tactical_stop_distance_pct,
            "tactical_stop_candidates": tactical_stop_candidates,
            "risk_per_share": risk_per_share,
            "target_1": target_1,
            "target_2": target_2,
            "expected_rr": actual_rr,
            "rr_capped": capped_target_1 != target_1,
            "rr_resistance_source": rr_resistance_source,
            "position_size": "Portfolio size required",
            "holding_style": V2_HOLDING_STYLE,
        }
    except Exception as e:
        logger.error(f"[Risk] Trade plan failed: {e}", exc_info=True)
        return None
