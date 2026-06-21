# screener.py — Fetch price data + compute indicators.
#
# Fix #6 — replaced per-ticker yf.download loop with chunked batch downloads
#   (yfinance's native multi-ticker mode with threads). 10-20× speed-up.
# Fix #5 — extracted `compute_series` / `latest_snapshot` so the recent-cross
#   scanner can reuse the same math.
# Pullback scanner — computes EMA20/50/200, RSI14, volume SMA20, and
# latest OHLCV context for bullish pullback criteria.
# Fix #7 — compute_rsi fills NaN with a neutral 50 so flat-history tickers
#   don't silently poison downstream comparisons.
import logging
import math
import pandas as pd
import yfinance as yf

from config import (
    EMA_FAST, EMA_MID, EMA_LONG, RSI_PERIOD,
    DATA_PERIOD, DATA_INTERVAL,
    MIN_DATA_ROWS, VOLUME_WINDOW, SL_SWING_LOOKBACK,
    ATR_PERIOD, ATR_SMA_WINDOW, HIGH_52W_LOOKBACK,
    RELATIVE_STRENGTH_LOOKBACK, RS_LOOKBACK_SHORT, RS_LOOKBACK_MEDIUM,
    RS_LOOKBACK_LONG, TREND_TEMPLATE_SMA_SHORT, TREND_TEMPLATE_SMA_MID,
    TREND_TEMPLATE_SMA_LONG, TREND_TEMPLATE_SMA200_RISING_LOOKBACK,
    VCP_CONTRACTION_LOOKBACK_SHORT,
    VCP_CONTRACTION_LOOKBACK_MID, VCP_CONTRACTION_LOOKBACK_LONG,
    VCP_HISTORY_LOOKBACK_DAYS,
    VCP_PIVOT_LOOKBACK,
)
from yfinance_cache import configure_yfinance_cache

logger = logging.getLogger(__name__)

# Chunk the batch request so one network blip doesn't lose the whole universe.
_CHUNK_SIZE = 200


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI via Wilder's smoothing. Neutral-fills NaN so flat series return 50."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Compute ATR with Wilder-style smoothing from a daily OHLC frame."""
    try:
        high = df["High"].squeeze()
        low = df["Low"].squeeze()
        close = df["Close"].squeeze()
        prev_close = close.shift(1)
        true_range = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return true_range.ewm(com=period - 1, min_periods=period).mean()
    except Exception as e:
        logger.warning(f"[Screener] ATR computation failed: {e}")
        return pd.Series(dtype="float64")


def compute_series(df: pd.DataFrame) -> dict | None:
    """
    Compute the full indicator series for one ticker's OHLCV frame.
    Returns OHLCV + EMA20/50/200 + RSI + volume SMA series, or None if
    the frame has too little history for a stable EMA_LONG.
    """
    if df is None or len(df) < MIN_DATA_ROWS:
        return None

    open_ = df["Open"].squeeze()
    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()
    atr = compute_atr(df, ATR_PERIOD)
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "ema20": close.ewm(span=EMA_FAST, adjust=False).mean(),
        "ema50": close.ewm(span=EMA_MID, adjust=False).mean(),
        "ema200": close.ewm(span=EMA_LONG, adjust=False).mean(),
        "ema_long": close.ewm(span=EMA_LONG, adjust=False).mean(),
        "sma50": close.rolling(TREND_TEMPLATE_SMA_SHORT).mean(),
        "sma150": close.rolling(TREND_TEMPLATE_SMA_MID).mean(),
        "sma200": close.rolling(TREND_TEMPLATE_SMA_LONG).mean(),
        "rsi": compute_rsi(close, RSI_PERIOD),
        "vol_sma20": volume.rolling(VOLUME_WINDOW).mean(),
        "atr": atr,
        "atr_sma20": atr.rolling(ATR_SMA_WINDOW).mean(),
    }


def _pct_range(high: pd.Series, low: pd.Series, close: float, lookback: int) -> float:
    """Return the high-low range over a lookback as a percent of close."""
    try:
        if close <= 0:
            return 0.0
        window_high = float(high.iloc[-lookback:].max())
        window_low = float(low.iloc[-lookback:].min())
        return (window_high - window_low) / close
    except Exception as e:
        logger.warning(f"[Screener] Range calculation failed: {e}")
        return 0.0


def _return_over_lookback(close: pd.Series, lookback: int) -> float:
    """Return percent change over a fixed trading-day lookback."""
    try:
        if len(close) <= lookback:
            return 0.0
        start = float(close.iloc[-lookback - 1])
        end = float(close.iloc[-1])
        if start == 0:
            return 0.0
        return ((end - start) / start) * 100
    except Exception as e:
        logger.warning(f"[Screener] Lookback return calculation failed: {e}")
        return 0.0


def _finite_or_none(value: object) -> float | None:
    """Return a finite float, or None for missing/invalid values."""
    try:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _record_missing(missing_reasons: list[str], field: str, reason: str) -> None:
    missing_reasons.append(f"{field} unavailable: {reason}")


def _last_finite(series: pd.Series, field: str, missing_reasons: list[str]) -> float | None:
    try:
        value = series.iloc[-1]
    except Exception:
        _record_missing(missing_reasons, field, "latest value missing")
        return None
    number = _finite_or_none(value)
    if number is None:
        _record_missing(missing_reasons, field, "latest value is not finite")
    return number


def _value_n_days_ago(
    series: pd.Series,
    lookback: int,
    field: str,
    missing_reasons: list[str],
) -> float | None:
    try:
        if len(series) <= lookback:
            _record_missing(missing_reasons, field, f"requires at least {lookback + 1} rows")
            return None
        value = series.iloc[-lookback - 1]
    except Exception:
        _record_missing(missing_reasons, field, "historical value missing")
        return None
    number = _finite_or_none(value)
    if number is None:
        _record_missing(missing_reasons, field, "historical value is not finite")
    return number


def _return_over_lookback_optional(
    close: pd.Series,
    lookback: int,
    field: str,
    missing_reasons: list[str],
) -> float | None:
    try:
        if len(close) <= lookback:
            _record_missing(missing_reasons, field, f"requires at least {lookback + 1} rows")
            return None
        start = _finite_or_none(close.iloc[-lookback - 1])
        end = _finite_or_none(close.iloc[-1])
        if start in (None, 0) or end is None:
            _record_missing(missing_reasons, field, "lookback values are not usable")
            return None
        return ((end - start) / start) * 100
    except Exception as e:
        logger.warning(f"[Screener] Optional lookback return calculation failed: {e}")
        _record_missing(missing_reasons, field, type(e).__name__)
        return None


def _window_extreme(
    series: pd.Series,
    lookback: int,
    field: str,
    missing_reasons: list[str],
    *,
    mode: str,
) -> float | None:
    try:
        window = series.iloc[-lookback:]
        if window.empty:
            _record_missing(missing_reasons, field, "window is empty")
            return None
        value = window.max() if mode == "max" else window.min()
    except Exception:
        _record_missing(missing_reasons, field, "window calculation failed")
        return None
    number = _finite_or_none(value)
    if number is None:
        _record_missing(missing_reasons, field, "window value is not finite")
    return number


def _series_tail_values(series: pd.Series, lookback: int) -> list[float | None]:
    """Return a JSON-safe numeric tail while preserving row alignment."""
    values: list[float | None] = []
    for value in series.iloc[-lookback:]:
        number = _finite_or_none(value)
        values.append(round(number, 6) if number is not None else None)
    return values


def _series_tail_dates(series: pd.Series, lookback: int) -> list[str]:
    """Return string dates aligned with a tail of a price series."""
    dates: list[str] = []
    for index_value in series.index[-lookback:]:
        dates.append(
            index_value.date().isoformat()
            if hasattr(index_value, "date")
            else str(index_value)
        )
    return dates


def _price_history(series: dict, lookback: int) -> dict:
    """Build bounded OHLCV history for shadow VCP diagnostics."""
    close = series["close"]
    return {
        "dates": _series_tail_dates(close, lookback),
        "high": _series_tail_values(series["high"], lookback),
        "low": _series_tail_values(series["low"], lookback),
        "close": _series_tail_values(close, lookback),
        "volume": _series_tail_values(series["volume"], lookback),
    }


def latest_snapshot(ticker: str, series: dict) -> dict | None:
    """Collapse a series dict into a single-row snapshot for the latest bar."""
    try:
        close = series["close"]
        high = series["high"]
        low = series["low"]
        volume = series["volume"]
        missing_reasons: list[str] = []
        data_quality_flags: list[str] = []
        today_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        if prev_close == 0:
            return None
        avg_volume = float(volume.iloc[-VOLUME_WINDOW:].mean())
        avg_volume_50 = float(volume.iloc[-50:].mean())
        dollar_volume = close * volume
        latest_index = close.index[-1]
        latest_bar_date = (
            latest_index.date().isoformat()
            if hasattr(latest_index, "date")
            else str(latest_index)
        )
        pivot_window = high.iloc[-VCP_PIVOT_LOOKBACK - 1:-1]
        pivot_low_window = low.iloc[-VCP_PIVOT_LOOKBACK - 1:-1]
        if pivot_window.empty:
            pivot_window = high.iloc[-VCP_PIVOT_LOOKBACK:]
        if pivot_low_window.empty:
            pivot_low_window = low.iloc[-VCP_PIVOT_LOOKBACK:]
        if len(close) < HIGH_52W_LOOKBACK:
            data_quality_flags.append(
                f"partial_52w_lookback:{len(close)}/{HIGH_52W_LOOKBACK}"
            )
        sma50 = _last_finite(series["sma50"], "sma50", missing_reasons)
        sma150 = _last_finite(series["sma150"], "sma150", missing_reasons)
        sma200 = _last_finite(series["sma200"], "sma200", missing_reasons)
        sma200_20d_ago = _value_n_days_ago(
            series["sma200"],
            TREND_TEMPLATE_SMA200_RISING_LOOKBACK,
            "sma200_20d_ago",
            missing_reasons,
        )
        high_52w = _window_extreme(
            high,
            HIGH_52W_LOOKBACK,
            "high_52w",
            missing_reasons,
            mode="max",
        )
        low_52w = _window_extreme(
            low,
            HIGH_52W_LOOKBACK,
            "low_52w",
            missing_reasons,
            mode="min",
        )
        return_63d = _return_over_lookback_optional(
            close,
            RS_LOOKBACK_SHORT,
            "return_63d",
            missing_reasons,
        )
        return_126d = _return_over_lookback_optional(
            close,
            RS_LOOKBACK_MEDIUM,
            "return_126d",
            missing_reasons,
        )
        return_252d = _return_over_lookback_optional(
            close,
            RS_LOOKBACK_LONG,
            "return_252d",
            missing_reasons,
        )
        if missing_reasons:
            data_quality_flags.append("missing_vcp_foundation_data")
        return {
            "ticker": ticker,
            "latest_bar_date": latest_bar_date,
            "open": float(series["open"].iloc[-1]),
            "high": float(high.iloc[-1]),
            "low": float(low.iloc[-1]),
            "close": today_close,
            "pct_change": ((today_close - prev_close) / prev_close) * 100,
            "ema20": float(series["ema20"].iloc[-1]),
            "ema50": float(series["ema50"].iloc[-1]),
            "ema200": float(series["ema200"].iloc[-1]),
            "ema_long": float(series["ema_long"].iloc[-1]),
            "sma50": sma50,
            "sma150": sma150,
            "sma200": sma200,
            "sma200_20d_ago": sma200_20d_ago,
            "rsi": float(series["rsi"].iloc[-1]),
            "volume": float(volume.iloc[-1]),
            "avg_volume": avg_volume,
            "avg_volume_50": avg_volume_50,
            "vol_sma20": float(series["vol_sma20"].iloc[-1]),
            "swing_low_5": float(low.iloc[-SL_SWING_LOOKBACK:].min()),
            "avg_dollar_volume": float(dollar_volume.iloc[-VOLUME_WINDOW:].mean()),
            "return_20d": _return_over_lookback(close, RELATIVE_STRENGTH_LOOKBACK),
            "return_63d": return_63d,
            "return_126d": return_126d,
            "return_252d": return_252d,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "range_5d_pct": _pct_range(high, low, today_close, VCP_CONTRACTION_LOOKBACK_SHORT),
            "range_10d_pct": _pct_range(high, low, today_close, VCP_CONTRACTION_LOOKBACK_MID),
            "range_20d_pct": _pct_range(high, low, today_close, VCP_CONTRACTION_LOOKBACK_LONG),
            "atr": float(series["atr"].iloc[-1]),
            "atr_sma20": float(series["atr_sma20"].iloc[-1]),
            "consolidation_volume": float(
                volume.iloc[-VCP_CONTRACTION_LOOKBACK_SHORT:].mean()
            ),
            "pivot": float(pivot_window.max()),
            "pivot_low": float(pivot_low_window.min()),
            "contraction_low": float(
                low.iloc[-VCP_CONTRACTION_LOOKBACK_MID:].min()
            ),
            "_history": _price_history(series, VCP_HISTORY_LOOKBACK_DAYS),
            "data_quality_flags": data_quality_flags,
            "missing_data_reasons": missing_reasons,
        }
    except (IndexError, ValueError, KeyError) as e:
        logger.warning(f"[Screener] {ticker}: snapshot error — {e}")
        return None


def _download_chunk(chunk: list[str]) -> dict[str, pd.DataFrame]:
    """Batch-fetch a chunk of tickers. Returns {ticker: frame} for successes."""
    if not chunk:
        return {}

    configure_yfinance_cache()
    df = yf.download(
        chunk,
        period=DATA_PERIOD,
        interval=DATA_INTERVAL,
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=True,
    )
    if df is None or df.empty:
        return {}

    out: dict[str, pd.DataFrame] = {}

    # yfinance returns single-level columns when called with exactly one ticker.
    if len(chunk) == 1:
        out[chunk[0]] = df
        return out

    # Otherwise columns are a MultiIndex keyed by ticker.
    if not isinstance(df.columns, pd.MultiIndex):
        logger.warning("[Screener] Expected MultiIndex for batch; got flat frame")
        return out

    available = set(df.columns.get_level_values(0))
    for t in chunk:
        if t not in available:
            continue
        sub = df[t].dropna(how="all")
        if not sub.empty:
            out[t] = sub
    return out


def batch_download(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """
    Chunked batch download for the full universe. A failing chunk logs and
    is skipped rather than taking the whole run down.
    """
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), _CHUNK_SIZE):
        chunk = tickers[i:i + _CHUNK_SIZE]
        try:
            out.update(_download_chunk(chunk))
        except Exception as e:
            logger.warning(
                f"[Screener] Chunk {i}-{i + len(chunk)} failed: "
                f"{type(e).__name__}: {e}"
            )
    return out


def screen_universe(tickers: list[str]) -> list[dict]:
    """Fetch + compute indicators + latest-bar snapshots for all tickers."""
    total = len(tickers)
    logger.info(f"[Screener] Batch-downloading {total} tickers...")
    frames = batch_download(tickers)
    logger.info(f"[Screener] Received data for {len(frames)}/{total} tickers")

    results: list[dict] = []
    for ticker, df in frames.items():
        series = compute_series(df)
        if series is None:
            continue
        snap = latest_snapshot(ticker, series)
        if snap is not None:
            results.append(snap)

    logger.info(f"[Screener] Done: {len(results)}/{total} snapshots computed")
    return results


def fetch_and_compute(ticker: str) -> dict | None:
    """Backward-compatible single-ticker convenience wrapper."""
    frames = batch_download([ticker])
    df = frames.get(ticker)
    if df is None:
        return None
    series = compute_series(df)
    if series is None:
        return None
    return latest_snapshot(ticker, series)
