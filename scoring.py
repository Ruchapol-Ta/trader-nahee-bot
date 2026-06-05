# scoring.py - V2 setup scoring and grades.
import logging

from config import (
    V2_SCORE_A_MIN,
    V2_SCORE_A_PLUS_MIN,
    V2_SCORE_B_MIN,
    V2_SCORE_C_MIN,
    V2_SCORE_WEIGHTS,
)

logger = logging.getLogger(__name__)


def grade_for_score(score: int | float) -> str:
    """Map a numeric V2 score to the configured quality grade."""
    try:
        score = float(score)
        if score >= V2_SCORE_A_PLUS_MIN:
            return "A+"
        if score >= V2_SCORE_A_MIN:
            return "A"
        if score >= V2_SCORE_B_MIN:
            return "B"
        if score >= V2_SCORE_C_MIN:
            return "C"
        return "Reject"
    except Exception as e:
        logger.error(f"[Scoring] Grade calculation failed: {e}", exc_info=True)
        return "Reject"


def score_candidate(
    market_regime: dict,
    liquidity: dict,
    relative_strength: dict,
    setup: dict,
    trade_plan: dict | None,
) -> dict:
    """Score a V2 candidate across the configured V2 quality categories."""
    try:
        checks = setup.get("checks", {})
        quality_scores = setup.get("quality_scores", {})
        category_scores = {
            "market_regime": V2_SCORE_WEIGHTS["market_regime"] if market_regime.get("is_valid") else 0,
            "liquidity": V2_SCORE_WEIGHTS["liquidity"] if liquidity.get("passed") else 0,
            "trend_structure": min(
                quality_scores.get(
                    "trend_structure",
                    V2_SCORE_WEIGHTS["trend_structure"] if checks.get("trend") else 0,
                ),
                V2_SCORE_WEIGHTS["trend_structure"],
            ),
            "relative_strength": V2_SCORE_WEIGHTS["relative_strength"]
            if relative_strength.get("passed") else 0,
            "high_52w_proximity": min(
                quality_scores.get(
                    "high_52w_proximity",
                    V2_SCORE_WEIGHTS["high_52w_proximity"] if checks.get("near_high") else 0,
                ),
                V2_SCORE_WEIGHTS["high_52w_proximity"],
            ),
            "consolidation_tightness": min(
                quality_scores.get(
                    "consolidation_tightness",
                    V2_SCORE_WEIGHTS["consolidation_tightness"]
                    if checks.get("range_tightening") else 0,
                ),
                V2_SCORE_WEIGHTS["consolidation_tightness"],
            ),
            "atr_contraction": min(
                quality_scores.get(
                    "atr_contraction",
                    V2_SCORE_WEIGHTS["atr_contraction"] if checks.get("atr_contraction") else 0,
                ),
                V2_SCORE_WEIGHTS["atr_contraction"],
            ),
            "volume_quality": quality_scores.get(
                "volume_quality",
                V2_SCORE_WEIGHTS["volume_quality"]
                if checks.get("volume_dry_up") and checks.get("breakout_volume") else 0,
            ),
            "risk_reward": V2_SCORE_WEIGHTS["risk_reward"]
            if trade_plan and trade_plan.get("structural_stop_distance_pct") is not None else 0,
        }
        score = int(sum(category_scores.values()))
        return {
            "score": score,
            "grade": grade_for_score(score),
            "category_scores": category_scores,
        }
    except Exception as e:
        logger.error(f"[Scoring] Candidate scoring failed: {e}", exc_info=True)
        return {
            "score": 0,
            "grade": "Reject",
            "category_scores": {key: 0 for key in V2_SCORE_WEIGHTS},
        }
