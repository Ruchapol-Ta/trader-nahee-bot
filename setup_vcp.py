# setup_vcp.py - V2 volatility-contraction breakout checks.
import logging
import math

from config import (
    TREND_TEMPLATE_MAX_52W_HIGH_DISTANCE,
    TREND_TEMPLATE_MIN_ABOVE_52W_LOW,
    VCP_ATR_CONTRACTION_RATIO,
    VCP_BREAKOUT_VOLUME_RATIO,
    VCP_MAX_52W_HIGH_DISTANCE,
    VCP_NEAR_BREAKOUT_THRESHOLD,
    VCP_RANGE_TIGHTENING_RATIO,
    VCP_USE_TREND_TEMPLATE_GATE,
    VCP_VOLUME_DRY_UP_RATIO,
)

logger = logging.getLogger(__name__)


def _bucket_score(value: float, full: float, mid: float, base: float, scores: tuple[int, int, int, int]) -> int:
    """Return bucketed score for lower-is-better ratios."""
    if value <= full:
        return scores[0]
    if value <= mid:
        return scores[1]
    if value <= base:
        return scores[2]
    return scores[3]


def _trend_score(close: float | None, ema50: float | None, trend_passed: bool) -> int:
    """Score bullish trend while penalizing names stretched far above the 50EMA."""
    if not trend_passed or close is None or ema50 in (None, 0):
        return 0
    distance = (close - ema50) / ema50
    if distance <= 0.12:
        return 15
    if distance <= 0.20:
        return 12
    if distance <= 0.30:
        return 8
    return 4


def _high_proximity_score(close: float | None, high_52w: float | None) -> int:
    """Score proximity to the 52-week high without using it as a hard filter."""
    if close is None or high_52w in (None, 0):
        return 0
    distance = (high_52w - close) / high_52w
    if distance <= 0.02:
        return 10
    if distance <= VCP_MAX_52W_HIGH_DISTANCE:
        return 7
    if distance <= 0.10:
        return 4
    return 0


def _volume_score(volume_dry_up_ratio: float, breakout_volume_ratio: float) -> int:
    """Score consolidation dry-up and breakout-day participation."""
    if volume_dry_up_ratio <= 0.70 and breakout_volume_ratio >= 1.25:
        return 10
    if volume_dry_up_ratio <= VCP_VOLUME_DRY_UP_RATIO and breakout_volume_ratio >= 1.10:
        return 6
    if volume_dry_up_ratio <= VCP_VOLUME_DRY_UP_RATIO and breakout_volume_ratio >= VCP_BREAKOUT_VOLUME_RATIO:
        return 1
    if volume_dry_up_ratio <= 0.90 or breakout_volume_ratio >= VCP_BREAKOUT_VOLUME_RATIO:
        return 1
    return 0


def _number(data: dict, key: str) -> float | None:
    """Read a finite numeric setup field."""
    try:
        value = data.get(key)
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception as e:
        logger.warning(f"[VCP] {data.get('ticker', '<unknown>')}: invalid {key}: {e}")
        return None


def _distance_from_high_pct(close: float | None, high_52w: float | None) -> float | None:
    if close is None or high_52w in (None, 0):
        return None
    return round(((high_52w - close) / high_52w) * 100, 2)


def _distance_above_low_pct(close: float | None, low_52w: float | None) -> float | None:
    if close is None or low_52w in (None, 0):
        return None
    return round(((close - low_52w) / low_52w) * 100, 2)


def evaluate_trend_template(data: dict) -> dict:
    """Evaluate Minervini-style Trend Template hard conditions."""
    close = _number(data, "close")
    sma50 = _number(data, "sma50")
    sma150 = _number(data, "sma150")
    sma200 = _number(data, "sma200")
    sma200_20d_ago = _number(data, "sma200_20d_ago")
    high_52w = _number(data, "high_52w")
    low_52w = _number(data, "low_52w")

    checks: list[tuple[str, bool | None, str, str]] = [
        ("close_above_sma50", None, "close > SMA50", "close <= SMA50"),
        ("close_above_sma150", None, "close > SMA150", "close <= SMA150"),
        ("close_above_sma200", None, "close > SMA200", "close <= SMA200"),
        ("sma_stack", None, "SMA50 > SMA150 > SMA200", "SMA50 <= SMA150 or SMA150 <= SMA200"),
        ("sma200_rising", None, "SMA200 rising over 20 trading days", "SMA200 not rising over 20 trading days"),
        (
            "above_52w_low",
            None,
            f"close >= {TREND_TEMPLATE_MIN_ABOVE_52W_LOW:.0%} above 52-week low",
            f"close < {TREND_TEMPLATE_MIN_ABOVE_52W_LOW:.0%} above 52-week low",
        ),
        (
            "near_52w_high",
            None,
            f"close within {TREND_TEMPLATE_MAX_52W_HIGH_DISTANCE:.0%} of 52-week high",
            f"close more than {TREND_TEMPLATE_MAX_52W_HIGH_DISTANCE:.0%} below 52-week high",
        ),
    ]

    missing: list[str] = []
    required = {
        "close": close,
        "sma50": sma50,
        "sma150": sma150,
        "sma200": sma200,
        "sma200_20d_ago": sma200_20d_ago,
        "high_52w": high_52w,
        "low_52w": low_52w,
    }
    for field, value in required.items():
        if value is None:
            missing.append(f"{field} unavailable")

    evaluated = {
        "close_above_sma50": close is not None and sma50 is not None and close > sma50,
        "close_above_sma150": close is not None and sma150 is not None and close > sma150,
        "close_above_sma200": close is not None and sma200 is not None and close > sma200,
        "sma_stack": (
            sma50 is not None
            and sma150 is not None
            and sma200 is not None
            and sma50 > sma150 > sma200
        ),
        "sma200_rising": (
            sma200 is not None
            and sma200_20d_ago is not None
            and sma200 > sma200_20d_ago
        ),
        "above_52w_low": (
            close is not None
            and low_52w not in (None, 0)
            and close >= low_52w * (1 + TREND_TEMPLATE_MIN_ABOVE_52W_LOW)
        ),
        "near_52w_high": (
            close is not None
            and high_52w not in (None, 0)
            and close >= high_52w * (1 - TREND_TEMPLATE_MAX_52W_HIGH_DISTANCE)
        ),
    }

    reasons: list[str] = []
    failures = list(missing)
    for key, _, pass_reason, fail_reason in checks:
        if evaluated[key]:
            reasons.append(pass_reason)
        else:
            failures.append(fail_reason)

    passed_count = sum(1 for value in evaluated.values() if value)
    score = round((passed_count / len(evaluated)) * 100, 2)
    return {
        "trend_template_pass": not failures,
        "trend_template_score": score,
        "trend_template_reasons": reasons,
        "trend_template_failures": failures,
        "trend_template_checks": evaluated,
        "distance_from_52w_high_pct": _distance_from_high_pct(close, high_52w),
        "distance_above_52w_low_pct": _distance_above_low_pct(close, low_52w),
    }


def evaluate_vcp_setup(data: dict) -> dict:
    """Evaluate the simple explainable VCP breakout setup rules."""
    try:
        close = _number(data, "close")
        ema50 = _number(data, "ema50")
        ema200 = _number(data, "ema200")
        high_52w = _number(data, "high_52w")
        range_5d = _number(data, "range_5d_pct")
        range_10d = _number(data, "range_10d_pct")
        range_20d = _number(data, "range_20d_pct")
        atr = _number(data, "atr")
        atr_sma20 = _number(data, "atr_sma20")
        consolidation_volume = _number(data, "consolidation_volume")
        avg_volume = _number(data, "avg_volume")
        volume = _number(data, "volume")
        pivot = _number(data, "pivot")
        trend_template = evaluate_trend_template(data)
        legacy_trend = bool(close and ema50 and ema200 and close > ema50 and close > ema200 and ema50 > ema200)
        trend_passed = (
            bool(trend_template["trend_template_pass"])
            if VCP_USE_TREND_TEMPLATE_GATE
            else legacy_trend
        )

        checks = {
            "trend": trend_passed,
            "legacy_trend": legacy_trend,
            "trend_template": bool(trend_template["trend_template_pass"]),
            "near_high": bool(close and high_52w and high_52w > 0 and ((high_52w - close) / high_52w) <= VCP_MAX_52W_HIGH_DISTANCE),
            "range_tightening": bool(
                range_5d is not None
                and range_10d is not None
                and range_20d is not None
                and range_5d <= range_20d * VCP_RANGE_TIGHTENING_RATIO
                and range_10d <= range_20d
            ),
            "atr_contraction": bool(atr is not None and atr_sma20 and atr <= atr_sma20 * VCP_ATR_CONTRACTION_RATIO),
            "volume_dry_up": bool(
                consolidation_volume is not None
                and avg_volume
                and consolidation_volume <= avg_volume * VCP_VOLUME_DRY_UP_RATIO
            ),
            "breakout_volume": bool(volume is not None and avg_volume and volume > avg_volume * VCP_BREAKOUT_VOLUME_RATIO),
            "breakout": bool(
                close is not None
                and pivot is not None
                and close > pivot
            ),
            "near_breakout": bool(
                close is not None
                and pivot is not None
                and pivot > 0
                and close <= pivot
                and close >= pivot * (1 - VCP_NEAR_BREAKOUT_THRESHOLD)
            ),
        }
        checks["breakout_or_near_breakout"] = bool(checks["breakout"] or checks["near_breakout"])

        range_ratio = (
            range_5d / range_20d
            if range_5d is not None and range_20d not in (None, 0)
            else 1.0
        )
        atr_ratio = (
            atr / atr_sma20
            if atr is not None and atr_sma20 not in (None, 0)
            else 1.0
        )
        volume_dry_up_ratio = (
            consolidation_volume / avg_volume
            if consolidation_volume is not None and avg_volume not in (None, 0)
            else 1.0
        )
        breakout_volume_ratio = (
            volume / avg_volume
            if volume is not None and avg_volume not in (None, 0)
            else 0.0
        )
        trend_score = 15 if checks["trend_template"] else (
            _trend_score(close, ema50, checks["trend"])
            if not VCP_USE_TREND_TEMPLATE_GATE
            else 0
        )
        high_score = _high_proximity_score(close, high_52w)
        tightness_score = _bucket_score(range_ratio, 0.60, 0.75, VCP_RANGE_TIGHTENING_RATIO, (10, 6, 2, 0))
        atr_score = _bucket_score(atr_ratio, 0.80, 0.85, VCP_ATR_CONTRACTION_RATIO, (10, 7, 3, 0))
        volume_score = _volume_score(volume_dry_up_ratio, breakout_volume_ratio)

        reject_reasons: list[str] = []
        if not checks["trend"]:
            if VCP_USE_TREND_TEMPLATE_GATE:
                detail = "; ".join(trend_template["trend_template_failures"][:3])
                reject_reasons.append(f"trend template failed: {detail}")
            else:
                reject_reasons.append("price not above 50EMA/200EMA with 50EMA > 200EMA")
        if not checks["breakout_or_near_breakout"]:
            reject_reasons.append("close is not above or within near-breakout range of pivot/resistance")

        passed = not reject_reasons
        reasons = [
            label for key, label in [
                ("trend", "trend structure bullish"),
                ("near_high", "near 52-week high"),
                ("range_tightening", "range tightening"),
                ("atr_contraction", "ATR contracting"),
                ("volume_dry_up", "volume dry-up"),
                ("breakout", "breakout above pivot"),
                ("near_breakout", "near pivot breakout"),
            ] if checks[key]
        ]
        return {
            "passed": passed,
            "checks": checks,
            "quality_scores": {
                "trend_structure": trend_score,
                "high_52w_proximity": high_score,
                "consolidation_tightness": tightness_score,
                "atr_contraction": atr_score,
                "volume_quality": volume_score,
            },
            **trend_template,
            "reasons": reasons,
            "reject_reasons": reject_reasons,
        }
    except Exception as e:
        logger.error(f"[VCP] Evaluation failed: {e}", exc_info=True)
        return {
            "passed": False,
            "checks": {},
            "reasons": [],
            "reject_reasons": [f"VCP evaluation failed: {type(e).__name__}"],
        }
