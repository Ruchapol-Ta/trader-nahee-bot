# recent_cross_scan.py — One-off broader scan for recent bullish pullbacks.
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    RECENT_CROSS_LOOKBACK_DAYS,
    RECENT_CROSS_MAX_SIGNALS,
    SL_SWING_LOOKBACK,
    VOLUME_WINDOW,
)
from logging_config import setup_logging
from screener import batch_download, compute_series
from universe import get_full_universe, UniverseLoadError
from signals import detect_signal, _with_risk_levels
from formatter import format_signal_message
from telegram_sender import send_message, send_error_alert

setup_logging()
logger = logging.getLogger(__name__)


def _snapshot_at(ticker: str, series: dict, offset: int) -> dict | None:
    """Build one historical snapshot where offset=1 is the latest bar."""
    try:
        close = series["close"]
        volume = series["volume"]
        idx = -offset
        prev_idx = idx - 1
        today_close = float(close.iloc[idx])
        prev_close = float(close.iloc[prev_idx])
        if prev_close == 0:
            return None
        return {
            "ticker": ticker,
            "open": float(series["open"].iloc[idx]),
            "high": float(series["high"].iloc[idx]),
            "low": float(series["low"].iloc[idx]),
            "close": today_close,
            "pct_change": ((today_close - prev_close) / prev_close) * 100,
            "ema20": float(series["ema20"].iloc[idx]),
            "ema50": float(series["ema50"].iloc[idx]),
            "ema200": float(series["ema200"].iloc[idx]),
            "rsi": float(series["rsi"].iloc[idx]),
            "volume": float(volume.iloc[idx]),
            "avg_volume": float(volume.iloc[idx - VOLUME_WINDOW + 1:idx + 1].mean()),
            "vol_sma20": float(series["vol_sma20"].iloc[idx]),
            "swing_low_5": float(series["low"].iloc[idx - SL_SWING_LOOKBACK + 1:idx + 1].min()),
        }
    except (IndexError, ValueError, KeyError) as e:
        logger.warning(f"[RecentScan] {ticker}: snapshot error — {e}")
        return None


def _scan_from_series(ticker: str, series: dict) -> dict | None:
    """Detect the most recent bullish pullback within the lookback window."""
    if len(series["close"]) < RECENT_CROSS_LOOKBACK_DAYS + max(SL_SWING_LOOKBACK, VOLUME_WINDOW):
        return None

    for offset in range(1, RECENT_CROSS_LOOKBACK_DAYS + 1):
        snap = _snapshot_at(ticker, series, offset)
        if snap is None or detect_signal(snap) != "BULLISH":
            continue
        enriched = _with_risk_levels(snap)
        if enriched is None:
            continue
        return {**enriched, "days_ago": offset - 1}
    return None


def main() -> None:
    """Run a one-off scan for bullish pullbacks in the recent lookback window."""
    start = datetime.now()
    logger.info("=" * 60)
    logger.info(
        f"[RecentScan] Bullish pullbacks in the last "
        f"{RECENT_CROSS_LOOKBACK_DAYS} trading days"
    )
    logger.info("=" * 60)

    try:
        tickers = get_full_universe()
    except UniverseLoadError as e:
        logger.error(f"[RecentScan] Universe load failed: {e}", exc_info=True)
        send_error_alert(f"Recent pullback scan universe load failed: {e}")
        return

    logger.info(f"[RecentScan] Batch-downloading {len(tickers)} tickers...")
    frames = batch_download(tickers)
    logger.info(
        f"[RecentScan] Received data for {len(frames)}/{len(tickers)} tickers"
    )

    hits: list[dict] = []
    for ticker, df in frames.items():
        series = compute_series(df)
        if series is None:
            continue
        hit = _scan_from_series(ticker, series)
        if hit:
            hits.append(hit)

    hits.sort(key=lambda x: (x["days_ago"], abs(x["rsi"] - 50)))
    capped = hits[:RECENT_CROSS_MAX_SIGNALS]

    logger.info(
        f"[RecentScan] Total bullish pullbacks: {len(hits)} → sending {len(capped)}"
    )

    if not capped:
        send_message(
            f"📊 *Recent Pullback Scan*\n\n"
            f"No bullish pullbacks found in the last "
            f"{RECENT_CROSS_LOOKBACK_DAYS} trading days. 💤"
        )
    else:
        divider = "─" * 30
        header = (
            f"📊 *Recent Pullback Scan*\n{divider}\n"
            f"Bullish pullbacks in last {RECENT_CROSS_LOOKBACK_DAYS} trading days\n"
            f"🟢 Hits: *{len(hits)}*\n"
            f"📌 Sending top *{len(capped)}*"
        )
        send_message(header)
        for hit in capped:
            msg = (
                format_signal_message(hit)
                + f"\n🗓️ Matched {hit['days_ago']} trading day(s) ago"
            )
            send_message(msg)

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"[RecentScan] Done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
