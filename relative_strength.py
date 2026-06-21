# relative_strength.py - V2 benchmark-relative performance checks.
import logging
import math

from config import (
    VCP_RS_MIN_PERCENTILE,
    VCP_RS_PREFERRED_PERCENTILE,
    VCP_USE_RS_PERCENTILE_GATE,
)

logger = logging.getLogger(__name__)

_RS_WEIGHTS = {
    "return_63d": 0.25,
    "return_126d": 0.35,
    "return_252d": 0.40,
}


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


def rs_window_coverage(data: dict) -> dict:
    """Return available RS windows and normalized weights for one snapshot."""
    available = {
        key: _valid_number(data.get(key)) is not None
        for key in _RS_WEIGHTS
    }
    if not (available["return_63d"] and available["return_126d"]):
        return {
            **available,
            "weight_63d": 0.0,
            "weight_126d": 0.0,
            "weight_252d": 0.0,
        }

    total_weight = sum(weight for key, weight in _RS_WEIGHTS.items() if available[key])
    return {
        **available,
        "weight_63d": round(_RS_WEIGHTS["return_63d"] / total_weight, 4),
        "weight_126d": round(_RS_WEIGHTS["return_126d"] / total_weight, 4),
        "weight_252d": round(
            (_RS_WEIGHTS["return_252d"] / total_weight)
            if available["return_252d"]
            else 0.0,
            4,
        ),
    }


def calculate_rs_composite(data: dict) -> tuple[float | None, dict]:
    """Calculate composite RS from 63d/126d/252d returns using available windows."""
    coverage = rs_window_coverage(data)
    if not (coverage["return_63d"] and coverage["return_126d"]):
        return None, coverage

    total_weight = sum(weight for key, weight in _RS_WEIGHTS.items() if coverage[key])
    composite = 0.0
    for return_key in _RS_WEIGHTS:
        value = _valid_number(data.get(return_key))
        if value is not None:
            composite += value * (_RS_WEIGHTS[return_key] / total_weight)
    return round(composite, 4), coverage


def rank_universe_rs_percentiles(snapshots: list[dict]) -> list[dict]:
    """Attach universe-based RS composite, percentile, and rank to snapshots."""
    enriched: list[dict] = []
    valid_scores: list[float] = []

    for snapshot in snapshots:
        row = dict(snapshot)
        composite, coverage = calculate_rs_composite(row)
        row["rs_composite"] = composite
        row["rs_window_coverage"] = coverage
        row["rs_percentile"] = None
        row["rs_rank"] = None
        if composite is not None:
            valid_scores.append(composite)
        enriched.append(row)

    if not valid_scores:
        return enriched

    unique_scores = sorted(set(valid_scores))
    score_to_percentile = {
        score: round(
            (sum(1 for other in valid_scores if other <= score) / len(valid_scores)) * 100,
            2,
        )
        for score in unique_scores
    }
    score_to_rank = {
        score: 1 + sum(1 for other in valid_scores if other > score)
        for score in unique_scores
    }

    for row in enriched:
        composite = row.get("rs_composite")
        if composite is not None:
            row["rs_percentile"] = score_to_percentile[composite]
            row["rs_rank"] = score_to_rank[composite]
    return enriched


def _benchmark_context(
    data: dict,
    spy_return_20d: float | None,
    qqq_return_20d: float | None,
) -> dict:
    stock_return = _valid_number(data.get("return_20d"))
    spy_return = _valid_number(spy_return_20d)
    qqq_return = _valid_number(qqq_return_20d)
    context = {
        "stock_return_20d": stock_return,
        "spy_return_20d": spy_return,
        "qqq_return_20d": qqq_return,
        "outperformed_spy": False,
        "outperformed_qqq": False,
    }
    if stock_return is not None and spy_return is not None:
        context["outperformed_spy"] = stock_return > spy_return
    if stock_return is not None and qqq_return is not None:
        context["outperformed_qqq"] = stock_return > qqq_return
    return context


def evaluate_relative_strength(
    data: dict,
    spy_return_20d: float | None,
    qqq_return_20d: float | None,
    log_lagging: bool = True,
) -> dict:
    """Evaluate RS percentile when available; otherwise fall back to SPY/QQQ context."""
    try:
        ticker = data.get("ticker", "<unknown>")
        benchmark_context = _benchmark_context(data, spy_return_20d, qqq_return_20d)
        rs_percentile = _valid_number(data.get("rs_percentile"))

        if VCP_USE_RS_PERCENTILE_GATE and rs_percentile is not None:
            rs_composite = _valid_number(data.get("rs_composite"))
            rs_rank = data.get("rs_rank")
            passed = rs_percentile >= VCP_RS_MIN_PERCENTILE
            preferred = rs_percentile >= VCP_RS_PREFERRED_PERCENTILE
            reasons = []
            if passed:
                reasons.append(f"RS percentile {rs_percentile:.1f} >= {VCP_RS_MIN_PERCENTILE:.0f}")
            if preferred:
                reasons.append(f"preferred RS leadership >= {VCP_RS_PREFERRED_PERCENTILE:.0f}")
            if not passed and log_lagging:
                logger.info(
                    f"[RelativeStrength] {ticker}: RS percentile {rs_percentile:.1f} "
                    f"below {VCP_RS_MIN_PERCENTILE:.0f}"
                )
            return {
                "passed": passed,
                "score": 15 if passed else 0,
                "reasons": reasons,
                "reject_reasons": [] if passed else [
                    f"RS percentile {rs_percentile:.1f} < {VCP_RS_MIN_PERCENTILE:.0f}"
                ],
                "rs_composite": rs_composite,
                "rs_percentile": rs_percentile,
                "rs_rank": rs_rank,
                "rs_window_coverage": data.get("rs_window_coverage"),
                "benchmark_context": benchmark_context,
            }

        stock_return = _valid_number(data.get("return_20d"))
        spy_return = _valid_number(spy_return_20d)
        qqq_return = _valid_number(qqq_return_20d)

        if stock_return is None or spy_return is None or qqq_return is None:
            return {
                "passed": False,
                "score": 0,
                "reasons": [],
                "reject_reasons": ["relative strength data unavailable"],
                "rs_composite": data.get("rs_composite"),
                "rs_percentile": rs_percentile,
                "rs_rank": data.get("rs_rank"),
                "rs_window_coverage": data.get("rs_window_coverage"),
                "benchmark_context": benchmark_context,
            }

        reasons: list[str] = []
        if stock_return > spy_return:
            reasons.append("outperformed SPY")
        if stock_return > qqq_return:
            reasons.append("outperformed QQQ")

        passed = bool(reasons)
        if not passed and log_lagging:
            logger.info(
                f"[RelativeStrength] {ticker}: lagged SPY/QQQ "
                f"({stock_return:.2f}% vs {spy_return:.2f}%/{qqq_return:.2f}%)"
            )
        return {
            "passed": passed,
            "score": 15 if passed else 0,
            "reasons": reasons,
            "reject_reasons": [] if passed else ["did not outperform SPY or QQQ"],
            "rs_composite": data.get("rs_composite"),
            "rs_percentile": rs_percentile,
            "rs_rank": data.get("rs_rank"),
            "rs_window_coverage": data.get("rs_window_coverage"),
            "benchmark_context": benchmark_context,
        }
    except Exception as e:
        logger.error(f"[RelativeStrength] Evaluation failed: {e}", exc_info=True)
        return {
            "passed": False,
            "score": 0,
            "reasons": [],
            "reject_reasons": [f"relative strength evaluation failed: {type(e).__name__}"],
            "rs_composite": None,
            "rs_percentile": None,
            "rs_rank": None,
            "rs_window_coverage": None,
            "benchmark_context": {},
        }
