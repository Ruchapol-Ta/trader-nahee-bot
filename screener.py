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
import pandas as pd
import yfinance as yf

from config import (
    EMA_FAST, EMA_MID, EMA_LONG, RSI_PERIOD,
    DATA_PERIOD, DATA_INTERVAL,
    MIN_DATA_ROWS, VOLUME_WINDOW, SL_SWING_LOOKBACK,
)

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
        "rsi": compute_rsi(close, RSI_PERIOD),
        "vol_sma20": volume.rolling(VOLUME_WINDOW).mean(),
    }


def latest_snapshot(ticker: str, series: dict) -> dict | None:
    """Collapse a series dict into a single-row snapshot for the latest bar."""
    try:
        close = series["close"]
        low = series["low"]
        volume = series["volume"]
        today_close = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        if prev_close == 0:
            return None
        return {
            "ticker": ticker,
            "open": float(series["open"].iloc[-1]),
            "high": float(series["high"].iloc[-1]),
            "low": float(low.iloc[-1]),
            "close": today_close,
            "pct_change": ((today_close - prev_close) / prev_close) * 100,
            "ema20": float(series["ema20"].iloc[-1]),
            "ema50": float(series["ema50"].iloc[-1]),
            "ema200": float(series["ema200"].iloc[-1]),
            "ema_long": float(series["ema_long"].iloc[-1]),
            "rsi": float(series["rsi"].iloc[-1]),
            "volume": float(volume.iloc[-1]),
            "avg_volume": float(volume.iloc[-VOLUME_WINDOW:].mean()),
            "vol_sma20": float(series["vol_sma20"].iloc[-1]),
            "swing_low_5": float(low.iloc[-SL_SWING_LOOKBACK:].min()),
        }
    except (IndexError, ValueError, KeyError) as e:
        logger.warning(f"[Screener] {ticker}: snapshot error — {e}")
        return None


def _download_chunk(chunk: list[str]) -> dict[str, pd.DataFrame]:
    """Batch-fetch a chunk of tickers. Returns {ticker: frame} for successes."""
    if not chunk:
        return {}

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
