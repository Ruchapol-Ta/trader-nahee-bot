# v2_engine.py - V2 Trade Qualification Engine orchestration.
import copy
import logging
from collections import Counter
from uuid import uuid4

from config import (
    ENABLE_POSITION_SIZING,
    ENABLE_SIGNAL_JOURNAL,
    ENABLE_V3_DECISION_LAYER,
    V2_MARKET_SYMBOLS,
    V2_MAX_NEW_POSITIONS_PER_DAY,
    V2_MAX_TRADE_SIGNALS,
    V2_MAX_WATCHLIST,
    V2_SETUP_TYPE,
)
from decision_engine import evaluate_signal_decision
from journal import journal_signals
from liquidity_filter import (
    enrich_with_market_metadata,
    evaluate_liquidity,
)
from market_regime import evaluate_market_regime
from relative_strength import evaluate_relative_strength
from risk_engine import build_trade_plan
from scoring import score_candidate
from screener import batch_download, compute_series, latest_snapshot, screen_universe
from setup_vcp import evaluate_vcp_setup
from telegram_sender import send_v2_market_summary, send_v2_report
from universe import get_v2_universe
from position_sizing import calculate_signal_position_size

logger = logging.getLogger(__name__)


def _new_diagnostics(scanned: int = 0) -> dict:
    """Create the V2 diagnostics counters used for funnel logging."""
    return {
        "funnel": {
            "scanned": scanned,
            "liquidity_passed": 0,
            "trend_passed": 0,
            "relative_strength_passed": 0,
            "high_52w_passed": 0,
            "consolidation_tightness_passed": 0,
            "atr_contraction_passed": 0,
            "volume_dry_up_passed": 0,
            "breakout_passed": 0,
            "hard_gate_passed": 0,
            "actual_breakout_candidates": 0,
            "near_breakout_candidates": 0,
            "A_plus_count": 0,
            "A_count": 0,
            "B_watchlist_count": 0,
            "C_count": 0,
            "rejected_count": 0,
            "final_setup_passed": 0,
        },
        "reject_reasons": Counter(),
        "near_misses": [],
    }


def _reject_bucket(reason: str) -> str:
    """Map a concrete reject reason to a stable aggregate diagnostics bucket."""
    if reason.startswith("price not above"):
        return "rejected_by_trend"
    if reason.startswith("did not outperform"):
        return "rejected_by_relative_strength"
    if "52-week high" in reason:
        return "rejected_by_52w_high"
    if "range is not tightening" in reason:
        return "rejected_by_consolidation_tightness"
    if "ATR is not contracting" in reason:
        return "rejected_by_atr_contraction"
    if "volume has not dried up" in reason:
        return "rejected_by_volume_dry_up"
    if "near-breakout range" in reason:
        return "rejected_by_breakout_or_near_breakout"
    if "close is not above pivot" in reason:
        return "rejected_by_breakout"
    if "volume <" in reason or "dollar volume <" in reason or "market cap <" in reason or "price <" in reason:
        return "rejected_by_liquidity"
    if "risk/reward" in reason:
        return "rejected_by_risk_reward"
    if "score" in reason:
        return "rejected_by_score"
    return "rejected_by_other"


def _record_rejects(diagnostics: dict | None, reasons: list[str]) -> None:
    """Aggregate reject reasons when diagnostics collection is enabled."""
    if diagnostics is None:
        return
    for reason in reasons:
        diagnostics["reject_reasons"][_reject_bucket(reason)] += 1


def _record_rejected_candidate(diagnostics: dict | None) -> None:
    """Count one rejected ticker in the aggregate diagnostics funnel."""
    if diagnostics is not None:
        diagnostics["funnel"]["rejected_count"] += 1


def _record_setup_funnel(diagnostics: dict | None, relative_strength: dict, setup: dict) -> None:
    """Record pass counts for each V2 setup stage."""
    if diagnostics is None:
        return
    checks = setup.get("checks", {})
    funnel = diagnostics["funnel"]
    if checks.get("trend"):
        funnel["trend_passed"] += 1
    if relative_strength.get("passed"):
        funnel["relative_strength_passed"] += 1
    if checks.get("near_high"):
        funnel["high_52w_passed"] += 1
    if checks.get("range_tightening"):
        funnel["consolidation_tightness_passed"] += 1
    if checks.get("atr_contraction"):
        funnel["atr_contraction_passed"] += 1
    if checks.get("volume_dry_up"):
        funnel["volume_dry_up_passed"] += 1
    if checks.get("breakout"):
        funnel["breakout_passed"] += 1


def _safe_ratio(numerator: float | None, denominator: float | None) -> float:
    """Return a rounded ratio for diagnostics, or 0 when data is unusable."""
    try:
        if numerator is None or denominator in (None, 0):
            return 0.0
        return round(float(numerator) / float(denominator), 2)
    except Exception:
        return 0.0


def _near_miss_summary(data: dict, setup: dict, score: dict, failed_conditions: list[str]) -> dict:
    """Build a compact near-miss diagnostics record."""
    try:
        close = float(data.get("close", 0) or 0)
        high_52w = float(data.get("high_52w", 0) or 0)
        distance = ((high_52w - close) / high_52w) * 100 if high_52w else 0.0
        checks = setup.get("checks", {})
        return {
            "ticker": data.get("ticker", "<unknown>"),
            "score": score.get("score", 0),
            "grade": score.get("grade", "Reject"),
            "failed_conditions": failed_conditions,
            "price": round(close, 2),
            "distance_from_52w_high_pct": round(distance, 2),
            "relative_strength_20d": round(float(data.get("return_20d", 0) or 0), 2),
            "atr_contraction_value": _safe_ratio(data.get("atr"), data.get("atr_sma20")),
            "volume_ratio": _safe_ratio(data.get("volume"), data.get("avg_volume")),
            "breakout_status": bool(checks.get("breakout")),
            "near_breakout_status": bool(checks.get("near_breakout")),
        }
    except Exception as e:
        logger.warning(f"[V2] Near-miss summary failed: {e}")
        return {
            "ticker": data.get("ticker", "<unknown>"),
            "score": 0,
            "grade": "Reject",
            "failed_conditions": failed_conditions,
        }


def _record_near_miss(
    diagnostics: dict | None,
    debug: bool,
    data: dict,
    setup: dict,
    score: dict,
    failed_conditions: list[str],
) -> None:
    """Collect rejected candidates for opt-in V2 debug output."""
    if diagnostics is None or not debug:
        return
    diagnostics["near_misses"].append(
        _near_miss_summary(data, setup, score, failed_conditions)
    )


def _log_diagnostics(diagnostics: dict, debug: bool) -> None:
    """Log aggregate funnel, reject buckets, and optional top near-misses."""
    funnel = diagnostics["funnel"]
    reject_reasons = dict(diagnostics["reject_reasons"])
    logger.info(
        "[V2] Funnel: "
        + " ".join(f"{key}={value}" for key, value in funnel.items())
    )
    logger.info(
        "[V2] Reject aggregation: "
        + (" ".join(f"{key}={value}" for key, value in sorted(reject_reasons.items())) or "none")
    )
    if not debug:
        return
    near_misses = sorted(
        diagnostics["near_misses"],
        key=lambda item: item.get("score", 0),
        reverse=True,
    )[:10]
    logger.info(f"[V2] Top near-miss candidates: {len(near_misses)}")
    for idx, item in enumerate(near_misses, start=1):
        logger.info(
            f"[V2] Near miss #{idx}: {item['ticker']} "
            f"score={item.get('score')} grade={item.get('grade')} "
            f"price={item.get('price')} dist_52w={item.get('distance_from_52w_high_pct')}% "
            f"rs20={item.get('relative_strength_20d')} "
            f"atr_ratio={item.get('atr_contraction_value')} "
            f"vol_ratio={item.get('volume_ratio')} "
            f"breakout={item.get('breakout_status')} "
            f"failed={'; '.join(item.get('failed_conditions', []))}"
        )


def load_market_regime() -> dict:
    """Fetch SPY/QQQ only and evaluate the market hard gate."""
    try:
        frames = batch_download(list(V2_MARKET_SYMBOLS))
        snapshots: dict[str, dict] = {}
        for symbol in V2_MARKET_SYMBOLS:
            frame = frames.get(symbol)
            if frame is None:
                continue
            series = compute_series(frame)
            if series is None:
                continue
            snapshot = latest_snapshot(symbol, series)
            if snapshot is not None:
                snapshots[symbol] = snapshot
        market_regime = evaluate_market_regime(snapshots)
        market_regime["market_data"] = snapshots
        return market_regime
    except Exception as e:
        logger.error(f"[V2] Market regime load failed: {e}", exc_info=True)
        return {
            "is_valid": False,
            "score": 0,
            "summary": "Invalid market regime",
            "reasons": [],
            "invalid_reasons": [f"market regime load failed: {type(e).__name__}"],
        }


def _reject(ticker: str, reasons: list[str]) -> None:
    """Log V2 rejected setup reasons for auditability."""
    try:
        logger.info(f"[V2] Reject {ticker}: {'; '.join(reasons)}")
    except Exception as e:
        logger.warning(f"[V2] Reject logging failed: {e}")


def _benchmark_returns(market_regime: dict) -> tuple[float, float]:
    """Read benchmark returns captured by load_market_regime when available."""
    try:
        market_data = market_regime.get("market_data", {})
        return (
            float(market_data.get("SPY", {}).get("return_20d", 0.0)),
            float(market_data.get("QQQ", {}).get("return_20d", 0.0)),
        )
    except Exception as e:
        logger.warning(f"[V2] Benchmark return read failed: {e}")
        return 0.0, 0.0


def _annotate_v3_outputs(
    trade_signals: list[dict],
    watchlist: list[dict],
    market_regime: dict,
) -> tuple[list[dict], list[dict]]:
    """Add optional Pre-V3 annotations without changing V2 selection."""
    if not ENABLE_V3_DECISION_LAYER and not ENABLE_POSITION_SIZING:
        return trade_signals, watchlist

    annotated_trade_signals = [copy.deepcopy(signal) for signal in trade_signals]
    annotated_watchlist = [copy.deepcopy(signal) for signal in watchlist]
    for signal in [*annotated_trade_signals, *annotated_watchlist]:
        if ENABLE_V3_DECISION_LAYER:
            decision = evaluate_signal_decision(
                signal,
                market_regime=market_regime,
                enabled=True,
            )
            if decision is not None:
                signal["v3_decision"] = decision
        if ENABLE_POSITION_SIZING:
            signal["v3_position_size"] = calculate_signal_position_size(signal)
    return annotated_trade_signals, annotated_watchlist


def qualify_snapshot(
    data: dict,
    market_regime: dict,
    spy_return: float,
    qqq_return: float,
    diagnostics: dict | None = None,
    debug: bool = False,
) -> dict | None:
    """Run one stock snapshot through V2 liquidity, RS, VCP, risk, and scoring."""
    try:
        ticker = data.get("ticker", "<unknown>")
        basic_liquidity = evaluate_liquidity(data, check_market_cap=False)
        if not basic_liquidity["passed"]:
            _record_rejects(diagnostics, basic_liquidity["reject_reasons"])
            _record_rejected_candidate(diagnostics)
            _reject(ticker, basic_liquidity["reject_reasons"])
            return None

        enriched = enrich_with_market_metadata(data)
        liquidity = evaluate_liquidity(enriched)
        if not liquidity["passed"]:
            _record_rejects(diagnostics, liquidity["reject_reasons"])
            _record_rejected_candidate(diagnostics)
            _reject(ticker, liquidity["reject_reasons"])
            return None

        relative_strength = evaluate_relative_strength(enriched, spy_return, qqq_return)
        setup = evaluate_vcp_setup(enriched)
        trade_plan = build_trade_plan(enriched)
        _record_setup_funnel(diagnostics, relative_strength, setup)

        reject_reasons: list[str] = []
        reject_reasons.extend(relative_strength.get("reject_reasons", []))
        reject_reasons.extend(setup.get("reject_reasons", []))
        if trade_plan is None:
            reject_reasons.append("risk/reward plan invalid")
        score = score_candidate(market_regime, liquidity, relative_strength, setup, trade_plan)
        if reject_reasons:
            _record_rejects(diagnostics, reject_reasons)
            _record_rejected_candidate(diagnostics)
            _record_near_miss(diagnostics, debug, enriched, setup, score, reject_reasons)
            _reject(ticker, reject_reasons)
            return None

        if diagnostics is not None:
            diagnostics["funnel"]["hard_gate_passed"] += 1
            if setup.get("checks", {}).get("breakout"):
                diagnostics["funnel"]["actual_breakout_candidates"] += 1
            elif setup.get("checks", {}).get("near_breakout"):
                diagnostics["funnel"]["near_breakout_candidates"] += 1

        grade = score["grade"]
        if setup.get("checks", {}).get("near_breakout") and not setup.get("checks", {}).get("breakout"):
            grade = "B" if score["score"] >= 65 else grade
            score = {
                **score,
                "raw_score": score["score"],
                "score": min(score["score"], 74),
                "grade": grade,
            }
        if grade == "Reject":
            grade_reasons = [f"score {score['score']} graded {grade}"]
            _record_rejects(diagnostics, grade_reasons)
            _record_rejected_candidate(diagnostics)
            _record_near_miss(diagnostics, debug, enriched, setup, score, grade_reasons)
            _reject(ticker, grade_reasons)
            return None

        pass_reasons = (
            market_regime.get("reasons", [])
            + liquidity.get("reasons", [])
            + relative_strength.get("reasons", [])
            + setup.get("reasons", [])
        )
        return {
            **enriched,
            "setup_type": V2_SETUP_TYPE,
            "trade_plan": trade_plan,
            "score": score["score"],
            "grade": grade,
            "raw_score": score.get("raw_score", score["score"]),
            "category_scores": score["category_scores"],
            "is_actual_breakout": bool(setup.get("checks", {}).get("breakout")),
            "is_near_breakout": bool(setup.get("checks", {}).get("near_breakout")),
            "pass_reasons": pass_reasons[:4],
            "invalid_condition": "None",
            "market_regime": market_regime.get("summary", "Unknown"),
        }
    except Exception as e:
        logger.error(f"[V2] Qualification failed: {e}", exc_info=True)
        return None


def run_v2_scan(debug: bool = False) -> dict:
    """Run the full V2 EOD scan with the market hard gate first."""
    try:
        logger.info("[V2] Starting Trade Qualification Engine scan")
        market_regime = load_market_regime()
        if not market_regime.get("is_valid"):
            logger.info(
                "[V2] Market regime invalid; skipping universe load and stock scan: "
                + "; ".join(market_regime.get("invalid_reasons", []))
            )
            sent = send_v2_market_summary(market_regime)
            return {
                "market_regime_valid": False,
                "messages_sent": sent,
                "scanned": 0,
                "liquidity_passed": 0,
                "setup_passed": 0,
                "grades": {},
            }

        tickers = get_v2_universe()
        logger.info(f"[V2] Screening {len(tickers)} V2 tickers")
        snapshots = screen_universe(tickers)
        spy_return, qqq_return = _benchmark_returns(market_regime)
        diagnostics = _new_diagnostics(scanned=len(snapshots))

        qualified: list[dict] = []
        liquidity_passed = 0
        setup_passed = 0

        for snapshot in snapshots:
            first_liquidity = evaluate_liquidity(snapshot, check_market_cap=False)
            if first_liquidity["passed"]:
                liquidity_passed += 1
                diagnostics["funnel"]["liquidity_passed"] += 1
            candidate = qualify_snapshot(
                snapshot,
                market_regime,
                spy_return,
                qqq_return,
                diagnostics=diagnostics,
                debug=debug,
            )
            if candidate is not None:
                setup_passed += 1
                qualified.append(candidate)

        qualified.sort(key=lambda item: item["score"], reverse=True)
        trade_cap = min(V2_MAX_TRADE_SIGNALS, V2_MAX_NEW_POSITIONS_PER_DAY)
        trade_signals = [
            item for item in qualified
            if item["grade"] in {"A+", "A"} and item.get("is_actual_breakout", True)
        ][:trade_cap]
        watchlist = [
            item for item in qualified
            if item["grade"] == "B"
        ][:V2_MAX_WATCHLIST]
        trade_signals, watchlist = _annotate_v3_outputs(trade_signals, watchlist, market_regime)

        grades = Counter(item["grade"] for item in qualified)
        diagnostics["funnel"]["A_plus_count"] = grades.get("A+", 0)
        diagnostics["funnel"]["A_count"] = grades.get("A", 0)
        diagnostics["funnel"]["B_watchlist_count"] = len(watchlist)
        diagnostics["funnel"]["C_count"] = grades.get("C", 0)
        diagnostics["funnel"]["final_setup_passed"] = len(trade_signals) + len(watchlist)
        near_misses = sorted(
            diagnostics["near_misses"],
            key=lambda item: item.get("score", 0),
            reverse=True,
        )[:10]
        top_candidates = [
            {
                "ticker": item.get("ticker"),
                "grade": item.get("grade"),
                "score": item.get("score"),
                "actual_breakout": bool(item.get("is_actual_breakout")),
                "near_breakout": bool(item.get("is_near_breakout")),
            }
            for item in qualified
            if item.get("grade") in {"A+", "A", "B"}
        ][:10]
        stats = {
            "scanned": len(snapshots),
            "liquidity_passed": liquidity_passed,
            "setup_passed": setup_passed,
            "grades": dict(grades),
            "trade_signals": len(trade_signals),
            "watchlist": len(watchlist),
            "funnel": dict(diagnostics["funnel"]),
            "reject_reasons": dict(diagnostics["reject_reasons"]),
            "near_misses": near_misses,
            "top_candidates": top_candidates,
        }
        logger.info(
            f"[V2] Scanned={stats['scanned']} liquidity={liquidity_passed} "
            f"setups={setup_passed} grades={dict(grades)}"
        )
        _log_diagnostics(diagnostics, debug)
        if ENABLE_SIGNAL_JOURNAL:
            run_id = str(uuid4())
            written = journal_signals(trade_signals, watchlist, run_id=run_id)
            logger.info(f"[V3] Journaled {written} selected signals run_id={run_id}")
        sent = send_v2_report(market_regime, trade_signals, watchlist, stats)
        return {
            "market_regime_valid": True,
            "messages_sent": sent,
            "funnel": stats["funnel"],
            "reject_reasons": stats["reject_reasons"],
            "near_misses": near_misses,
            **stats,
        }
    except Exception as e:
        logger.error(f"[V2] Scan failed: {e}", exc_info=True)
        raise
