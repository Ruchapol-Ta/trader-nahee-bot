# formatter.py — Format Telegram alert messages.
#
# Fix #3 — label reads "Scanned at" (the time we generated the message),
#   not "Signal at" (which implied real-time intraday detection).
# Fix #20 — market timezone is pulled from config instead of hardcoded.
from datetime import datetime
import pytz

from config import (
    EMA_FAST, EMA_MID, EMA_LONG,
    VOLUME_HIGH_RATIO,
    MARKET_TIMEZONE,
)

_MARKET_TZ = pytz.timezone(MARKET_TIMEZONE)
_DIVIDER = "─" * 30


def _fmt_volume(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return str(int(v))


def format_signal_message(data: dict) -> str:
    """Format a full-detail alert for a single signal."""
    ticker = data["ticker"]
    close = data["close"]
    open_ = data["open"]
    low = data["low"]
    pct = data["pct_change"]
    rsi = data["rsi"]
    volume = data["volume"]
    vol_sma20 = data["vol_sma20"]

    pct_emoji = "📈" if pct >= 0 else "📉"
    pct_str = f"{pct:+.2f}%"
    vol_ratio = volume / vol_sma20 if vol_sma20 > 0 else 1.0
    vol_flag = " 🔥" if vol_ratio >= VOLUME_HIGH_RATIO else ""

    scanned_at = datetime.now(_MARKET_TZ).strftime("%Y-%m-%d %H:%M %Z")

    lines = [
        f"🟢 *{ticker}* — BULLISH PULLBACK",
        _DIVIDER,
        f"{pct_emoji} Close:     *${close:.2f}*  ({pct_str})",
        f"🕯️ Open/Low: ${open_:.2f} / ${low:.2f}",
        f"📈 EMA {EMA_FAST}:    ${data['ema20']:.2f}",
        f"📈 EMA {EMA_MID}:    ${data['ema50']:.2f}",
        f"📈 EMA {EMA_LONG}:   ${data['ema200']:.2f}",
        f"⚡ RSI 14:   {rsi:.1f}",
        f"📦 Volume:   {_fmt_volume(volume)}{vol_flag}  (SMA20 {_fmt_volume(vol_sma20)})",
        _DIVIDER,
        f"🎯 Entry:    *${close:.2f}*",
        f"🔴 SL:       *${data['sl']:.2f}*  (swing low -1%)",
        f"🟢 TP2:      *${data['tp2']:.2f}*  (2R)",
        f"🟢 TP3:      *${data['tp3']:.2f}*  (3R)",
        _DIVIDER,
        f"🕐 Scanned at: {scanned_at}",
        f"#{ticker} #bullish",
    ]
    return "\n".join(lines)


def format_summary_message(signals: list[dict]) -> str:
    """Summary header sent before individual alerts."""
    today = datetime.now(_MARKET_TZ).strftime("%b %d, %Y")

    return "\n".join([
        "📊 *Signal Bot*",
        _DIVIDER,
        f"📅 {today} — EOD Scan Complete",
        "",
        f"🟢 Bullish pullbacks: *{len(signals)}*",
        f"📌 Total alerts: *{len(signals)}*",
        _DIVIDER,
        "Details below 👇",
    ])
