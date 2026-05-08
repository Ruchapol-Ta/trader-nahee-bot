# smoke_test.py — Offline end-to-end test against a small ticker list.
# Prints formatted messages to stdout instead of sending to Telegram.
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from logging_config import setup_logging
from screener import screen_universe
from signals import filter_signals
from formatter import format_signal_message, format_summary_message

setup_logging()
logger = logging.getLogger(__name__)

SMOKE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
    "NFLX", "JPM", "BAC", "V", "MA", "WMT", "HD", "PG", "KO", "PEP",
    "DIS", "XOM",
]


def main() -> None:
    start = datetime.now()
    logger.info("=" * 60)
    logger.info(f"[SmokeTest] Running pipeline on {len(SMOKE_TICKERS)} tickers")
    logger.info("=" * 60)

    screener_results = screen_universe(SMOKE_TICKERS)
    logger.info(f"[SmokeTest] Screener returned {len(screener_results)} valid rows")

    if screener_results:
        sample = screener_results[0]
        logger.info(
            f"[SmokeTest] Sample row ({sample['ticker']}): "
            f"close=${sample['close']:.2f} "
            f"EMA20=${sample['ema20']:.2f} "
            f"EMA50=${sample['ema50']:.2f} "
            f"EMA200=${sample['ema200']:.2f} "
            f"RSI={sample['rsi']:.1f}"
        )

    signals = filter_signals(screener_results)
    logger.info(f"[SmokeTest] Signal filter yielded {len(signals)} alerts")

    print("\n" + "=" * 60)
    print("FORMATTED OUTPUT (would be sent to Telegram)")
    print("=" * 60)

    if not signals:
        print("\n[no signals — pipeline OK but nothing qualified today]\n")
    else:
        print("\n" + format_summary_message(signals))
        for s in signals:
            print("\n" + "-" * 40)
            print(format_signal_message(s))

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"[SmokeTest] Done in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
