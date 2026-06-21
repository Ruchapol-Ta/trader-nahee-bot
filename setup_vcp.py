# setup_vcp.py - V2 volatility-contraction breakout checks.
import logging
import math

from config import (
    TREND_TEMPLATE_MAX_52W_HIGH_DISTANCE,
    TREND_TEMPLATE_MIN_ABOVE_52W_LOW,
    VCP_ATR_CONTRACTION_RATIO,
    VCP_BASE_LOOKBACK_DAYS,
    VCP_BASE_MAX_DAYS,
    VCP_BASE_MIN_DAYS,
    VCP_BREAKOUT_VOLUME_RATIO,
    VCP_FINAL_CONTRACTION_MAX_DEPTH,
    VCP_FINAL_CONTRACTION_PREFERRED_DEPTH,
    VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH,
    VCP_HANDLE_SHELF_CLUSTER_PCT,
    VCP_HANDLE_SHELF_LOOKBACK,
    VCP_MAX_BASE_DEPTH,
    VCP_MAX_52W_HIGH_DISTANCE,
    VCP_MAX_CONTRACTION_DAYS,
    VCP_MAX_PIVOT_EXTENSION,
    VCP_MAX_CONTRACTION_DEPTH,
    VCP_MIN_BASE_DEPTH,
    VCP_MIN_CONTRACTION_DAYS,
    VCP_MIN_CONTRACTION_DEPTH,
    VCP_MIN_CONTRACTION_RECOVERY,
    VCP_MIN_CONTRACTIONS,
    VCP_MIN_LEAD_CONTRACTION_DEPTH,
    VCP_NEAR_BREAKOUT_THRESHOLD,
    VCP_ONE_DAY_SPIKE_THRESHOLD,
    VCP_PREFERRED_BASE_DEPTH,
    VCP_PREFERRED_CONTRACTIONS,
    VCP_PRIOR_UPTREND_LOOKBACK,
    VCP_PRIOR_UPTREND_MIN_RETURN,
    VCP_RANGE_TIGHTENING_RATIO,
    VCP_SWING_NOISE_THRESHOLD,
    VCP_SWING_WINDOW,
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


def _mean(values: list[float]) -> float | None:
    usable = [float(value) for value in values if math.isfinite(float(value))]
    if not usable:
        return None
    return sum(usable) / len(usable)


def _as_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _extract_price_history(data: dict) -> tuple[dict | None, list[str]]:
    """Return clean aligned OHLCV arrays for shadow VCP diagnostics."""
    raw = data.get("_history")
    if not isinstance(raw, dict):
        return None, ["price history unavailable for new VCP engine"]

    required = ("dates", "high", "low", "close", "volume")
    if any(not isinstance(raw.get(key), list) for key in required):
        return None, ["price history fields unavailable for new VCP engine"]

    row_count = min(len(raw[key]) for key in required)
    clean = {key: [] for key in required}
    dropped = 0
    for index in range(row_count):
        high = _as_float(raw["high"][index])
        low = _as_float(raw["low"][index])
        close = _as_float(raw["close"][index])
        volume = _as_float(raw["volume"][index])
        if (
            high is None
            or low is None
            or close is None
            or volume is None
            or high <= 0
            or low <= 0
            or close <= 0
            or high < low
        ):
            dropped += 1
            continue
        clean["dates"].append(str(raw["dates"][index]))
        clean["high"].append(high)
        clean["low"].append(low)
        clean["close"].append(close)
        clean["volume"].append(volume)

    reasons: list[str] = []
    if len(clean["close"]) < VCP_BASE_MIN_DAYS:
        reasons.append(
            f"price history too short for new VCP engine: "
            f"{len(clean['close'])}/{VCP_BASE_MIN_DAYS} rows"
        )
    if dropped:
        reasons.append(f"price history dropped {dropped} unusable rows")
    return (clean if not reasons or len(clean["close"]) >= VCP_BASE_MIN_DAYS else None), reasons


def _strong_trend_template_context(data: dict) -> bool:
    close = _number(data, "close")
    sma50 = _number(data, "sma50")
    sma150 = _number(data, "sma150")
    sma200 = _number(data, "sma200")
    sma200_20d_ago = _number(data, "sma200_20d_ago")
    return bool(
        close is not None
        and sma50 is not None
        and sma150 is not None
        and sma200 is not None
        and sma200_20d_ago is not None
        and close > sma50 > sma150 > sma200
        and sma200 > sma200_20d_ago
    )


def _is_one_day_high_spike(high: list[float], close: list[float], index: int) -> bool:
    if not high or not close or index < 0 or index >= len(high) or close[index] <= 0:
        return False
    wick_ratio = (high[index] - close[index]) / close[index]
    if index == 0:
        nearby_close = max(close[:min(len(close), 3)])
    elif index >= len(high) - 1:
        nearby_close = max(close[max(0, index - 2):index + 1])
    else:
        nearby_close = max(close[index - 1], close[index], close[index + 1])
    return bool(
        wick_ratio >= VCP_ONE_DAY_SPIKE_THRESHOLD
        and high[index] > nearby_close * (1 + VCP_ONE_DAY_SPIKE_THRESHOLD)
    )


def _swing_points(
    high: list[float],
    low: list[float],
    close: list[float],
    mode: str,
    window: int,
) -> list[dict]:
    """Find meaningful local swings while suppressing tiny noise and one-day spikes."""
    points: list[dict] = []
    if len(close) < (window * 2) + 1:
        return points
    for index in range(window, len(close) - window):
        left = index - window
        right = index + window + 1
        if mode == "high":
            value = high[index]
            neighbors = high[left:index] + high[index + 1:right]
            local_floor = min(low[left:right])
            if value < max(neighbors):
                continue
            if value <= local_floor * (1 + VCP_SWING_NOISE_THRESHOLD):
                continue
            if _is_one_day_high_spike(high, close, index):
                continue
            points.append({"index": index, "type": "high", "value": value})
        else:
            value = low[index]
            neighbors = low[left:index] + low[index + 1:right]
            local_ceiling = max(high[left:right])
            if value > min(neighbors):
                continue
            if value >= local_ceiling * (1 - VCP_SWING_NOISE_THRESHOLD):
                continue
            points.append({"index": index, "type": "low", "value": value})
    return points


def _alternating_swing_events(high: list[float], low: list[float], close: list[float]) -> list[dict]:
    """Compress raw swing points into alternating high/low events."""
    events = (
        _swing_points(high, low, close, "high", VCP_SWING_WINDOW)
        + _swing_points(high, low, close, "low", VCP_SWING_WINDOW)
    )
    events.sort(key=lambda item: (item["index"], 0 if item["type"] == "high" else 1))

    alternating: list[dict] = []
    for event in events:
        if not alternating:
            alternating.append(event)
            continue
        last = alternating[-1]
        if event["type"] == last["type"]:
            if event["type"] == "high" and event["value"] >= last["value"]:
                alternating[-1] = event
            elif event["type"] == "low" and event["value"] <= last["value"]:
                alternating[-1] = event
            continue
        if event["index"] == last["index"]:
            continue
        alternating.append(event)

    while alternating and alternating[0]["type"] != "high":
        alternating.pop(0)
    return alternating


def _volume_profile(
    close: list[float],
    volume: list[float],
    start_index: int,
    end_index: int,
    avg_volume_50: float | None,
) -> dict:
    segment_volume = volume[start_index:end_index + 1]
    avg_volume = _mean(segment_volume)
    down_volume = [
        volume[index]
        for index in range(max(start_index + 1, 1), end_index + 1)
        if close[index] < close[index - 1]
    ]
    down_volume_avg = _mean(down_volume)
    baseline = avg_volume_50 or _mean(volume[-50:])
    ratio = (
        round(avg_volume / baseline, 3)
        if avg_volume is not None and baseline not in (None, 0)
        else None
    )
    return {
        "avg_volume": round(avg_volume, 2) if avg_volume is not None else None,
        "down_volume_avg": round(down_volume_avg, 2) if down_volume_avg is not None else None,
        "volume_ratio_to_50d": ratio,
    }


def _recovery_after_low(
    high: list[float],
    swing_high: float,
    swing_low: float,
    low_index: int,
) -> tuple[bool, int | None, float | None, float | None]:
    if swing_high <= swing_low:
        return False, None, None, None
    required_recovery = swing_low + ((swing_high - swing_low) * VCP_MIN_CONTRACTION_RECOVERY)
    search_end = min(len(high), low_index + VCP_MAX_CONTRACTION_DAYS + 1)
    best_index = None
    best_value = None
    for index in range(low_index + 1, search_end):
        if best_value is None or high[index] > best_value:
            best_value = high[index]
            best_index = index
    if best_value is None:
        return False, None, None, None
    recovery_ratio = (best_value - swing_low) / (swing_high - swing_low)
    return best_value >= required_recovery, best_index, best_value, round(recovery_ratio, 3)


def _build_contractions(
    *,
    dates: list[str],
    high: list[float],
    low: list[float],
    close: list[float],
    volume: list[float],
    base_offset: int,
    avg_volume_50: float | None,
) -> list[dict]:
    events = _alternating_swing_events(high, low, close)
    if high and low and close and len(close) >= VCP_MIN_CONTRACTION_DAYS:
        lookahead_end = min(len(low), VCP_MAX_CONTRACTION_DAYS + 1)
        first_high = float(high[0])
        first_window_high = max(high[:min(len(high), VCP_SWING_WINDOW + 1)])
        first_existing_high_index = next(
            (event["index"] for event in events if event["type"] == "high"),
            lookahead_end,
        )
        leading_low_points = [
            point for point in _swing_points(high, low, close, "low", VCP_SWING_WINDOW)
            if 0 < point["index"] < min(lookahead_end, first_existing_high_index)
        ]
        if leading_low_points:
            first_low_index = leading_low_points[0]["index"]
            first_low = leading_low_points[0]["value"]
        else:
            first_low_segment = low[1:min(lookahead_end, first_existing_high_index)]
            first_low = min(first_low_segment) if first_low_segment else None
            first_low_index = (
                low.index(first_low, 1, min(lookahead_end, first_existing_high_index))
                if first_low is not None
                else None
            )
        first_pullback = (
            (first_high - float(first_low)) / first_high
            if first_high > 0 and first_low is not None
            else 0
        )
        starts_at_meaningful_high = (
            first_high >= first_window_high * (1 - VCP_HANDLE_SHELF_CLUSTER_PCT)
            and first_pullback >= VCP_MIN_CONTRACTION_DEPTH
            and first_pullback <= VCP_MAX_CONTRACTION_DEPTH
            and first_low_index is not None
            and (first_low_index + 1) >= VCP_MIN_CONTRACTION_DAYS
            and not _is_one_day_high_spike(high, close, 0)
        )
        if starts_at_meaningful_high and (not events or events[0]["index"] > 0):
            events = [
                {"index": 0, "type": "high", "value": first_high},
                {"index": first_low_index, "type": "low", "value": float(first_low)},
                *events,
            ]
    contractions: list[dict] = []
    for index in range(len(events) - 1):
        start = events[index]
        end = events[index + 1]
        if start["type"] != "high" or end["type"] != "low":
            continue
        duration = end["index"] - start["index"] + 1
        if duration < VCP_MIN_CONTRACTION_DAYS or duration > VCP_MAX_CONTRACTION_DAYS:
            continue
        swing_high = float(start["value"])
        swing_low = float(end["value"])
        if swing_high <= 0 or swing_low >= swing_high:
            continue
        pullback_ratio = (swing_high - swing_low) / swing_high
        if pullback_ratio < VCP_MIN_CONTRACTION_DEPTH:
            continue
        if pullback_ratio > VCP_MAX_CONTRACTION_DEPTH:
            continue
        recovered, recovery_index, recovery_high, recovery_ratio = _recovery_after_low(
            high,
            swing_high,
            swing_low,
            end["index"],
        )
        if not recovered:
            continue
        volume_profile = _volume_profile(
            close,
            volume,
            start["index"],
            end["index"],
            avg_volume_50,
        )
        contractions.append({
            "start_index": start["index"],
            "end_index": end["index"],
            "history_start_index": base_offset + start["index"],
            "history_end_index": base_offset + end["index"],
            "history_recovery_index": base_offset + recovery_index if recovery_index is not None else None,
            "start_date": dates[start["index"]],
            "end_date": dates[end["index"]],
            "recovery_date": dates[recovery_index] if recovery_index is not None else None,
            "swing_high": round(swing_high, 2),
            "swing_low": round(swing_low, 2),
            "recovery_high": round(recovery_high, 2) if recovery_high is not None else None,
            "recovery_ratio": recovery_ratio,
            "pullback_ratio": round(pullback_ratio, 4),
            "pullback_pct": round(pullback_ratio * 100, 2),
            "duration_days": duration,
            "avg_volume": volume_profile["avg_volume"],
            "down_volume_avg": volume_profile["down_volume_avg"],
            "volume_ratio_to_50d": volume_profile["volume_ratio_to_50d"],
        })
    return contractions


def _select_contraction_sequence(candidates: list[dict]) -> list[dict]:
    """Choose the strongest non-overlapping 2-3 contraction sequence."""
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: (item["start_index"], item["end_index"]))
    non_overlapping: list[dict] = []
    for candidate in ordered:
        if not non_overlapping or candidate["start_index"] > non_overlapping[-1]["end_index"]:
            non_overlapping.append(candidate)
    if len(non_overlapping) <= VCP_PREFERRED_CONTRACTIONS:
        return non_overlapping

    best_score = -1.0
    best_sequence = non_overlapping[:VCP_PREFERRED_CONTRACTIONS]
    for length in range(VCP_MIN_CONTRACTIONS, VCP_PREFERRED_CONTRACTIONS + 1):
        for start in range(0, len(non_overlapping) - length + 1):
            sequence = non_overlapping[start:start + length]
            depths = [float(item["pullback_ratio"]) for item in sequence]
            tightening = _tightening_diagnostics(depths)
            score = (
                tightening["tightening_score"]
                + (length * 8)
                + max(0, 20 - (depths[-1] * 100))
                - (sequence[-1]["end_index"] * 0.01)
            )
            if score > best_score:
                best_score = score
                best_sequence = sequence
    return best_sequence


def _down_volume_shrinking(contractions: list[dict]) -> bool | None:
    down_volumes = [
        contraction.get("down_volume_avg")
        for contraction in contractions
        if contraction.get("down_volume_avg") is not None
    ]
    if len(down_volumes) < 2:
        return None
    return all(current <= previous * 1.10 for previous, current in zip(down_volumes, down_volumes[1:]))


def _prior_uptrend(history: dict, base_start_index: int, data: dict) -> dict:
    lookback = min(VCP_PRIOR_UPTREND_LOOKBACK, base_start_index)
    if lookback < 20:
        return {
            "prior_uptrend_pass": _strong_trend_template_context(data),
            "prior_uptrend_pct": None,
            "prior_uptrend_reason": (
                "strong current Trend Template context"
                if _strong_trend_template_context(data)
                else "insufficient pre-base history"
            ),
        }

    start = history["close"][base_start_index - lookback]
    end = history["close"][base_start_index]
    if start <= 0:
        return {
            "prior_uptrend_pass": False,
            "prior_uptrend_pct": None,
            "prior_uptrend_reason": "unusable pre-base price",
        }

    prior_pct = (end - start) / start
    prior_high_start = max(0, base_start_index - 126)
    prior_highs = history["high"][prior_high_start:base_start_index + 1]
    near_relative_high = bool(prior_highs and history["high"][base_start_index] >= max(prior_highs) * 0.95)
    strong_template = _strong_trend_template_context(data)

    if prior_pct >= VCP_PRIOR_UPTREND_MIN_RETURN:
        passed = True
        reason = f"pre-base advance {prior_pct:.1%}"
    elif prior_pct >= 0.10 and near_relative_high:
        passed = True
        reason = f"pre-base advance {prior_pct:.1%} near multi-month high"
    elif strong_template and near_relative_high and prior_pct >= 0.05:
        passed = True
        reason = "strong Trend Template context near multi-month high"
    else:
        passed = False
        reason = f"pre-base advance {prior_pct:.1%} below requirement"

    return {
        "prior_uptrend_pass": passed,
        "prior_uptrend_pct": round(prior_pct * 100, 2),
        "prior_uptrend_reason": reason,
    }


def _tightening_diagnostics(depths: list[float]) -> dict:
    if len(depths) < 2:
        return {
            "tightening_score": 0,
            "tightening_pass": False,
            "tightening_warning": "fewer than two contractions",
        }

    first = depths[0]
    final = depths[-1]
    final_smaller = final < first
    final_within_shadow_limit = final <= VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH
    middle_warning = None
    if len(depths) >= 3:
        middle_depths = depths[1:-1]
        if any(depth > first * 1.15 for depth in middle_depths):
            middle_warning = "middle contraction is imperfect but final contraction tightened"

    score = 0
    if final_smaller:
        score += 45
    if final <= VCP_FINAL_CONTRACTION_MAX_DEPTH:
        score += 30
    elif final <= VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH:
        score += 18
    if len(depths) >= VCP_PREFERRED_CONTRACTIONS:
        score += 15
    if middle_warning is None:
        score += 10
    else:
        score += 4

    warning = middle_warning
    if final > VCP_FINAL_CONTRACTION_MAX_DEPTH and final <= VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH:
        warning = "final contraction above preferred depth"
    if not final_smaller:
        warning = "final contraction is not smaller than first contraction"
    if not final_within_shadow_limit:
        warning = f"final contraction depth above {VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH:.0%}"

    return {
        "tightening_score": min(score, 100),
        "tightening_pass": bool(final_smaller and final_within_shadow_limit),
        "tightening_warning": warning,
    }


def _volume_quality(contractions: list[dict]) -> dict:
    if not contractions:
        return {
            "volume_dry_up_ratio": None,
            "final_vs_prior_volume_ratio": None,
            "volume_quality": "unavailable",
            "volume_warning": None,
        }
    final = contractions[-1]
    final_volume = _as_float(final.get("avg_volume"))
    ratio_to_50d = _as_float(final.get("volume_ratio_to_50d"))
    prior_volumes = [
        _as_float(item.get("avg_volume"))
        for item in contractions[:-1]
        if _as_float(item.get("avg_volume")) is not None
    ]
    prior_avg = _mean(prior_volumes) if prior_volumes else None
    ratio_to_prior = (
        final_volume / prior_avg
        if final_volume is not None and prior_avg not in (None, 0)
        else None
    )

    if ratio_to_50d is None:
        quality = "unavailable"
        warning = None
    elif ratio_to_50d <= VCP_VOLUME_DRY_UP_RATIO and (ratio_to_prior is None or ratio_to_prior <= 0.95):
        quality = "dry_up"
        warning = None
    elif ratio_to_50d > 1.20 and ratio_to_prior is not None and ratio_to_prior > 1.10:
        quality = "expanding"
        warning = "final_contraction_volume_expanding"
    else:
        quality = "neutral"
        warning = None

    return {
        "volume_dry_up_ratio": round(ratio_to_50d, 3) if ratio_to_50d is not None else None,
        "final_vs_prior_volume_ratio": round(ratio_to_prior, 3) if ratio_to_prior is not None else None,
        "volume_quality": quality,
        "volume_warning": warning,
    }


def _candidate_base_windows(history: dict, data: dict) -> list[dict]:
    total_rows = len(history["close"])
    recent_offset = max(0, total_rows - VCP_BASE_LOOKBACK_DAYS)
    recent = {key: values[recent_offset:] for key, values in history.items()}
    events = _alternating_swing_events(recent["high"], recent["low"], recent["close"])
    high_events = [event for event in events if event["type"] == "high"]
    if not high_events and recent["high"]:
        highest_index = recent["high"].index(max(recent["high"]))
        high_events = [{"index": highest_index, "type": "high", "value": recent["high"][highest_index]}]

    candidates: list[dict] = []
    for event in high_events:
        start_index = recent_offset + event["index"]
        duration = total_rows - start_index
        if duration < VCP_BASE_MIN_DAYS or duration > VCP_BASE_MAX_DAYS:
            continue

        base = {key: values[start_index:] for key, values in history.items()}
        base_high = max(base["high"])
        base_low = min(base["low"])
        current_close = base["close"][-1]
        start_close = base["close"][0]
        base_range = base_high - base_low
        base_depth = (base_range / base_high) if base_high > 0 else None
        recovery_ratio = ((current_close - base_low) / base_range) if base_range > 0 else None
        long_downtrend = bool(
            start_close > 0
            and current_close < start_close * 0.85
            and (recovery_ratio is None or recovery_ratio < 0.45)
        )
        prior = _prior_uptrend(history, start_index, data)
        base_score = 0
        if prior["prior_uptrend_pass"]:
            base_score += 30
        if base_depth is not None:
            if base_depth <= VCP_PREFERRED_BASE_DEPTH:
                base_score += 25
            elif base_depth <= VCP_MAX_BASE_DEPTH:
                base_score += 15
        if recovery_ratio is not None and recovery_ratio >= VCP_MIN_CONTRACTION_RECOVERY:
            base_score += 15
        if not long_downtrend:
            base_score += 10
        if current_close >= base_low + (base_range * 0.50):
            base_score += 10
        if VCP_BASE_MIN_DAYS <= duration <= VCP_BASE_MAX_DAYS:
            base_score += 10

        candidates.append({
            "base": base,
            "start_index": start_index,
            "start_date": history["dates"][start_index],
            "base_duration_days": duration,
            "base_high": base_high,
            "base_low": base_low,
            "base_depth": base_depth,
            "base_recovery_ratio": round(recovery_ratio, 3) if recovery_ratio is not None else None,
            "base_is_long_downtrend": long_downtrend,
            "prior": prior,
            "base_score": base_score,
        })
    return candidates


def _base_reject_reasons(candidate: dict) -> list[str]:
    reasons: list[str] = []
    prior = candidate.get("prior") or {}
    base_depth = candidate.get("base_depth")
    recovery = candidate.get("base_recovery_ratio")
    if prior.get("prior_uptrend_pass") is not True:
        reasons.append("prior uptrend not confirmed")
    if base_depth is None:
        reasons.append("base depth unavailable")
    elif base_depth > VCP_MAX_BASE_DEPTH:
        reasons.append(f"base depth {base_depth:.1%} > {VCP_MAX_BASE_DEPTH:.0%}")
    elif base_depth < VCP_MIN_BASE_DEPTH:
        reasons.append(f"base depth {base_depth:.1%} < {VCP_MIN_BASE_DEPTH:.0%}")
    if candidate.get("base_is_long_downtrend"):
        reasons.append("base window resembles long downtrend")
    if recovery is not None and recovery < VCP_MIN_CONTRACTION_RECOVERY:
        reasons.append("base has not recovered enough from low")
    return reasons


def _vcp_quality_score(
    *,
    prior_uptrend_pass: bool | None,
    base_depth: float | None,
    contraction_count: int,
    tightening_score: int,
    final_depth: float | None,
    volume_quality: str | None,
    pivot_identified: bool,
) -> int:
    score = 0
    if prior_uptrend_pass:
        score += 20
    if base_depth is not None:
        if base_depth <= VCP_PREFERRED_BASE_DEPTH:
            score += 20
        elif base_depth <= VCP_MAX_BASE_DEPTH:
            score += 14
    if contraction_count >= VCP_PREFERRED_CONTRACTIONS:
        score += 20
    elif contraction_count >= VCP_MIN_CONTRACTIONS:
        score += 14
    score += min(15, round((tightening_score / 100) * 15))
    if final_depth is not None:
        if final_depth <= VCP_FINAL_CONTRACTION_PREFERRED_DEPTH:
            score += 10
        elif final_depth <= VCP_FINAL_CONTRACTION_MAX_DEPTH:
            score += 7
        elif final_depth <= VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH:
            score += 4
    if volume_quality == "dry_up":
        score += 10
    elif volume_quality == "neutral":
        score += 5
    if pivot_identified:
        score += 5
    return min(score, 100)


def detect_vcp_contractions(data: dict) -> dict:
    """Detect a Minervini-style contraction sequence for shadow diagnostics."""
    history, history_reasons = _extract_price_history(data)
    if history is None:
        return {
            "passed": False,
            "contraction_count": 0,
            "contractions": [],
            "contraction_depths": [],
            "base_depth": None,
            "base_duration_days": None,
            "final_contraction_depth": None,
            "volume_dry_up_ratio": None,
            "final_vs_prior_volume_ratio": None,
            "volume_quality": "unavailable",
            "down_volume_shrinking": None,
            "prior_uptrend_pass": None,
            "prior_uptrend_pct": None,
            "prior_uptrend_reason": "price history unavailable",
            "tightening_score": 0,
            "tightening_pass": False,
            "tightening_warning": None,
            "vcp_quality_score": 0,
            "reject_reasons": history_reasons or ["price history unavailable for new VCP engine"],
            "warning_flags": [],
        }

    avg_volume_50 = _number(data, "avg_volume_50")
    base_candidates = _candidate_base_windows(history, data)
    evaluated_candidates: list[dict] = []
    rejected_base_reasons: list[str] = []
    for candidate in base_candidates:
        base_reasons = _base_reject_reasons(candidate)
        if base_reasons:
            rejected_base_reasons.extend(base_reasons)
            continue
        base = candidate["base"]
        raw_contractions = _build_contractions(
            dates=base["dates"],
            high=base["high"],
            low=base["low"],
            close=base["close"],
            volume=base["volume"],
            base_offset=candidate["start_index"],
            avg_volume_50=avg_volume_50,
        )
        selected = _select_contraction_sequence(raw_contractions)
        depths = [float(contraction["pullback_ratio"]) for contraction in selected]
        sequence_reject_reason = None
        if depths and depths[0] < VCP_MIN_LEAD_CONTRACTION_DEPTH:
            sequence_reject_reason = (
                f"lead contraction depth {depths[0]:.1%} < {VCP_MIN_LEAD_CONTRACTION_DEPTH:.0%}"
            )
            selected = []
            depths = []
        tightening = _tightening_diagnostics(depths)
        volume = _volume_quality(selected)
        score = (
            candidate["base_score"]
            + (len(selected) * 12)
            + tightening["tightening_score"]
            + (10 if volume["volume_quality"] == "dry_up" else 0)
        )
        evaluated_candidates.append({
            **candidate,
            "raw_contractions": raw_contractions,
            "selected": selected,
            "depths": depths,
            "tightening": tightening,
            "volume": volume,
            "sequence_reject_reason": sequence_reject_reason,
            "candidate_score": score,
        })

    if not evaluated_candidates:
        best_base = max(base_candidates, key=lambda item: item["base_score"]) if base_candidates else None
        base_reasons = _base_reject_reasons(best_base) if best_base else []
        reject_reasons = sorted(set(
            base_reasons
            or rejected_base_reasons
            or ["no candidate VCP base window"]
        ))
        if best_base is None:
            prior = {
                "prior_uptrend_pass": None,
                "prior_uptrend_pct": None,
                "prior_uptrend_reason": "no candidate base window",
            }
            base_depth = None
            base_duration_days = None
            base_start_date = None
            base_recovery_ratio = None
        else:
            prior = best_base["prior"]
            base_depth = best_base["base_depth"]
            base_duration_days = best_base["base_duration_days"]
            base_start_date = best_base["start_date"]
            base_recovery_ratio = best_base["base_recovery_ratio"]
        return {
            "passed": False,
            "contraction_count": 0,
            "contractions": [],
            "contraction_depths": [],
            "base_depth": round(base_depth * 100, 2) if base_depth is not None else None,
            "base_duration_days": base_duration_days,
            "base_start_date": base_start_date,
            "base_recovery_ratio": base_recovery_ratio,
            "final_contraction_depth": None,
            "volume_dry_up_ratio": None,
            "final_vs_prior_volume_ratio": None,
            "volume_quality": "unavailable",
            "down_volume_shrinking": None,
            "prior_uptrend_pass": prior["prior_uptrend_pass"],
            "prior_uptrend_pct": prior["prior_uptrend_pct"],
            "prior_uptrend_reason": prior["prior_uptrend_reason"],
            "tightening_score": 0,
            "tightening_pass": False,
            "tightening_warning": None,
            "vcp_quality_score": 0,
            "reject_reasons": reject_reasons,
            "warning_flags": history_reasons,
        }

    best = max(evaluated_candidates, key=lambda item: item["candidate_score"])
    selected = best["selected"]
    depths = best["depths"]
    contraction_depths = [round(depth * 100, 2) for depth in depths]
    contraction_count = len(selected)
    base_depth = best["base_depth"]
    base_duration_days = best["base_duration_days"]
    final_depth = depths[-1] if depths else None
    tightening = best["tightening"]
    volume = best["volume"]
    down_volume_shrinking = _down_volume_shrinking(selected)
    prior = best["prior"]

    reject_reasons: list[str] = []
    warning_flags: list[str] = list(history_reasons)
    if base_duration_days < VCP_BASE_MIN_DAYS:
        reject_reasons.append(f"base duration {base_duration_days}d < {VCP_BASE_MIN_DAYS}d")
    if base_duration_days > VCP_BASE_MAX_DAYS:
        reject_reasons.append(f"base duration {base_duration_days}d > {VCP_BASE_MAX_DAYS}d")
    if base_depth is None:
        reject_reasons.append("base depth unavailable")
    elif base_depth < VCP_MIN_BASE_DEPTH:
        reject_reasons.append(f"base depth {base_depth:.1%} < {VCP_MIN_BASE_DEPTH:.0%}")
    elif base_depth > VCP_PREFERRED_BASE_DEPTH:
        warning_flags.append("base_depth_above_preferred")
    if contraction_count < VCP_MIN_CONTRACTIONS:
        reject_reasons.append(
            best.get("sequence_reject_reason")
            or f"contraction count {contraction_count} < {VCP_MIN_CONTRACTIONS}"
        )
    elif contraction_count < VCP_PREFERRED_CONTRACTIONS:
        warning_flags.append("preferred_contractions_missing")
    if tightening["tightening_warning"]:
        warning_flags.append(tightening["tightening_warning"])
    if contraction_count >= VCP_MIN_CONTRACTIONS and not tightening["tightening_pass"]:
        reject_reasons.append(tightening["tightening_warning"] or "tightening structure failed")
    if final_depth is None:
        reject_reasons.append("final contraction unavailable")
    elif final_depth > VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH:
        reject_reasons.append(
            f"final contraction depth {final_depth:.1%} > {VCP_FINAL_CONTRACTION_SHADOW_MAX_DEPTH:.0%}"
        )
    elif final_depth > VCP_FINAL_CONTRACTION_MAX_DEPTH:
        warning_flags.append("final_contraction_above_preferred")
    if volume["volume_quality"] == "unavailable":
        warning_flags.append("final_contraction_volume_unavailable")
    elif volume["volume_warning"]:
        warning_flags.append(volume["volume_warning"])
    if down_volume_shrinking is False:
        warning_flags.append("down_volume_not_shrinking")

    return {
        "passed": not reject_reasons,
        "contraction_count": contraction_count,
        "contractions": selected,
        "contraction_depths": contraction_depths,
        "base_depth": round(base_depth * 100, 2) if base_depth is not None else None,
        "base_duration_days": base_duration_days,
        "base_start_date": best["start_date"],
        "base_recovery_ratio": best["base_recovery_ratio"],
        "final_contraction_depth": round(final_depth * 100, 2) if final_depth is not None else None,
        "volume_dry_up_ratio": volume["volume_dry_up_ratio"],
        "final_vs_prior_volume_ratio": volume["final_vs_prior_volume_ratio"],
        "volume_quality": volume["volume_quality"],
        "down_volume_shrinking": down_volume_shrinking,
        "prior_uptrend_pass": prior["prior_uptrend_pass"],
        "prior_uptrend_pct": prior["prior_uptrend_pct"],
        "prior_uptrend_reason": prior["prior_uptrend_reason"],
        "tightening_score": tightening["tightening_score"],
        "tightening_pass": tightening["tightening_pass"],
        "tightening_warning": tightening["tightening_warning"],
        "vcp_quality_score": _vcp_quality_score(
            prior_uptrend_pass=prior["prior_uptrend_pass"],
            base_depth=base_depth,
            contraction_count=contraction_count,
            tightening_score=tightening["tightening_score"],
            final_depth=final_depth,
            volume_quality=volume["volume_quality"],
            pivot_identified=False,
        ),
        "_base": best["base"],
        "reject_reasons": reject_reasons,
        "warning_flags": sorted(set(warning_flags)),
    }


def detect_final_contraction_pivot(data: dict, contraction_result: dict) -> dict:
    """Derive a shadow pivot from the high of the final contraction."""
    close = _number(data, "close")
    contractions = contraction_result.get("contractions") or []
    base = contraction_result.get("_base")
    base = base if isinstance(base, dict) else None
    if close is None:
        return {
            "pivot_price": None,
            "distance_to_pivot_pct": None,
            "pivot_status": "no_pivot",
            "pivot_source": None,
            "is_extended": False,
            "extension_reason": None,
            "reject_reasons": ["close unavailable for new VCP pivot"],
            "warning_flags": [],
        }
    if not contractions:
        return {
            "pivot_price": None,
            "distance_to_pivot_pct": None,
            "pivot_status": "no_pivot",
            "pivot_source": None,
            "is_extended": False,
            "extension_reason": None,
            "reject_reasons": ["no identifiable final contraction pivot"],
            "warning_flags": [],
        }

    final = contractions[-1]
    pivot = _as_float(final.get("swing_high"))
    pivot_source = "final_contraction_high"
    pivot_index = final.get("start_index")
    if base and isinstance(base.get("high"), list):
        shelf_start = max(int(final.get("end_index") or 0), len(base["high"]) - VCP_HANDLE_SHELF_LOOKBACK)
        shelf_highs = base["high"][shelf_start:]
        if shelf_highs:
            shelf_max = max(shelf_highs)
            cluster_count = sum(
                1 for value in shelf_highs
                if value >= shelf_max * (1 - VCP_HANDLE_SHELF_CLUSTER_PCT)
            )
            if cluster_count >= 2 and (pivot is None or shelf_max >= pivot * 0.98):
                pivot = shelf_max
                pivot_source = "handle_shelf_high_cluster"
                pivot_index = shelf_start + shelf_highs.index(shelf_max)

    if pivot in (None, 0):
        return {
            "pivot_price": None,
            "distance_to_pivot_pct": None,
            "pivot_status": "no_pivot",
            "pivot_source": None,
            "is_extended": False,
            "extension_reason": None,
            "reject_reasons": ["final contraction high unavailable"],
            "warning_flags": [],
        }

    extension = (close - pivot) / pivot
    distance_to_pivot_pct = ((pivot - close) / pivot) * 100
    warning_flags: list[str] = []
    reject_reasons: list[str] = []
    pivot_age = (len(base["high"]) - 1 - int(pivot_index)) if base and pivot_index is not None else None
    stale_pivot = pivot_age is not None and pivot_age > (VCP_HANDLE_SHELF_LOOKBACK * 2)
    extension_reason = None
    if extension > VCP_MAX_PIVOT_EXTENSION and not stale_pivot:
        pivot_status = "extended"
        reject_reasons.append(f"price more than {VCP_MAX_PIVOT_EXTENSION:.0%} above final-contraction pivot")
        warning_flags.append("price_extended_above_pivot")
        extension_reason = f"price {extension:.1%} above {pivot_source}"
    elif extension > VCP_MAX_PIVOT_EXTENSION and stale_pivot:
        pivot_status = "breaking_out"
        warning_flags.append("pivot_stale_extension_not_classified")
        extension_reason = "pivot is stale; extension not classified"
    elif close > pivot:
        pivot_status = "breaking_out"
    elif close >= pivot * (1 - VCP_NEAR_BREAKOUT_THRESHOLD):
        pivot_status = "near_pivot"
    else:
        pivot_status = "below_pivot"

    return {
        "pivot_price": round(pivot, 2),
        "distance_to_pivot_pct": round(distance_to_pivot_pct, 2),
        "pivot_status": pivot_status,
        "pivot_source": pivot_source,
        "pivot_age_days": pivot_age,
        "is_extended": pivot_status == "extended",
        "extension_reason": extension_reason,
        "reject_reasons": reject_reasons,
        "warning_flags": warning_flags,
    }


def evaluate_new_vcp_engine(data: dict) -> dict:
    """Run the shadow Minervini-style VCP engine without production gating."""
    contractions = detect_vcp_contractions(data)
    pivot = detect_final_contraction_pivot(data, contractions)
    reject_reasons = [
        *contractions.get("reject_reasons", []),
        *pivot.get("reject_reasons", []),
    ]
    warning_flags = sorted(set([
        *contractions.get("warning_flags", []),
        *pivot.get("warning_flags", []),
    ]))
    quality_score = _vcp_quality_score(
        prior_uptrend_pass=contractions.get("prior_uptrend_pass"),
        base_depth=(
            contractions.get("base_depth") / 100
            if contractions.get("base_depth") is not None
            else None
        ),
        contraction_count=contractions.get("contraction_count", 0),
        tightening_score=int(contractions.get("tightening_score") or 0),
        final_depth=(
            contractions.get("final_contraction_depth") / 100
            if contractions.get("final_contraction_depth") is not None
            else None
        ),
        volume_quality=contractions.get("volume_quality"),
        pivot_identified=pivot.get("pivot_price") is not None,
    )
    return {
        "passed": not reject_reasons,
        "engine_version": "vcp_shadow_swing_pivot_v1",
        "contraction_count": contractions.get("contraction_count", 0),
        "contraction_depths": contractions.get("contraction_depths", []),
        "contractions": contractions.get("contractions", []),
        "base_depth": contractions.get("base_depth"),
        "base_duration_days": contractions.get("base_duration_days"),
        "base_start_date": contractions.get("base_start_date"),
        "base_recovery_ratio": contractions.get("base_recovery_ratio"),
        "final_contraction_depth": contractions.get("final_contraction_depth"),
        "volume_dry_up_ratio": contractions.get("volume_dry_up_ratio"),
        "final_vs_prior_volume_ratio": contractions.get("final_vs_prior_volume_ratio"),
        "volume_quality": contractions.get("volume_quality"),
        "down_volume_shrinking": contractions.get("down_volume_shrinking"),
        "prior_uptrend_pass": contractions.get("prior_uptrend_pass"),
        "prior_uptrend_pct": contractions.get("prior_uptrend_pct"),
        "prior_uptrend_reason": contractions.get("prior_uptrend_reason"),
        "tightening_score": contractions.get("tightening_score"),
        "tightening_pass": contractions.get("tightening_pass"),
        "tightening_warning": contractions.get("tightening_warning"),
        "pivot_price": pivot.get("pivot_price"),
        "distance_to_pivot_pct": pivot.get("distance_to_pivot_pct"),
        "pivot_status": pivot.get("pivot_status"),
        "pivot_source": pivot.get("pivot_source"),
        "pivot_age_days": pivot.get("pivot_age_days"),
        "is_extended": pivot.get("is_extended"),
        "extension_reason": pivot.get("extension_reason"),
        "vcp_quality_score": quality_score,
        "reject_reasons": reject_reasons,
        "warning_flags": warning_flags,
    }


def _vcp_comparison(current_passed: bool, current_pivot: float | None, new_engine: dict) -> dict:
    new_passed = bool(new_engine.get("passed"))
    if current_passed and new_passed:
        agreement = "both_passed"
    elif current_passed and not new_passed:
        agreement = "current_only"
    elif not current_passed and new_passed:
        agreement = "new_engine_only"
    else:
        agreement = "both_failed"
    return {
        "current_vcp_logic_passed": current_passed,
        "new_vcp_engine_passed": new_passed,
        "agreement": agreement,
        "current_pivot": current_pivot,
        "new_pivot": new_engine.get("pivot_price"),
        "new_pivot_status": new_engine.get("pivot_status"),
        "new_contraction_count": new_engine.get("contraction_count"),
        "new_final_contraction_depth": new_engine.get("final_contraction_depth"),
    }


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
        new_vcp_engine = evaluate_new_vcp_engine(data)
        vcp_engine_comparison = _vcp_comparison(passed, pivot, new_vcp_engine)
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
            "current_vcp_logic": {
                "passed": passed,
                "checks": checks,
                "pivot": pivot,
                "reject_reasons": list(reject_reasons),
            },
            "new_vcp_engine": new_vcp_engine,
            "vcp_engine_comparison": vcp_engine_comparison,
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
