# liquidity_filter.py - V2 price, volume, dollar-volume, market-cap checks.
import logging
import math

import yfinance as yf

from config import (
    V2_MIN_AVG_DOLLAR_VOLUME,
    V2_MIN_AVG_VOLUME,
    V2_MIN_MARKET_CAP,
    V2_MIN_PRICE,
)
from yfinance_cache import configure_yfinance_cache

logger = logging.getLogger(__name__)


def _finite_float(data: dict, key: str, default: float | None = None) -> float | None:
    """Safely coerce a snapshot value to a finite float."""
    try:
        value = data.get(key, default)
        if value is None:
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except Exception as e:
        logger.warning(f"[Liquidity] {data.get('ticker', '<unknown>')}: invalid {key}: {e}")
        return None


def evaluate_liquidity(
    data: dict,
    check_market_cap: bool = True,
    log_market_cap_warning: bool = True,
) -> dict:
    """Apply V2 liquidity rules and return pass/fail reasons."""
    try:
        ticker = data.get("ticker", "<unknown>")
        close = _finite_float(data, "close")
        avg_volume = _finite_float(data, "avg_volume")
        avg_dollar_volume = _finite_float(data, "avg_dollar_volume")
        market_cap = _finite_float(data, "market_cap")

        reasons: list[str] = []
        reject_reasons: list[str] = []

        if close is None or close < V2_MIN_PRICE:
            reject_reasons.append(f"price < {V2_MIN_PRICE:.2f}")
        else:
            reasons.append("price/liquidity floor passed")

        if avg_volume is None or avg_volume < V2_MIN_AVG_VOLUME:
            reject_reasons.append(f"20d avg volume < {V2_MIN_AVG_VOLUME}")
        else:
            reasons.append("20d avg volume passed")

        if avg_dollar_volume is None or avg_dollar_volume < V2_MIN_AVG_DOLLAR_VOLUME:
            reject_reasons.append(f"20d avg dollar volume < {V2_MIN_AVG_DOLLAR_VOLUME}")
        else:
            reasons.append("20d avg dollar volume passed")

        if not check_market_cap:
            reasons.append("market cap check deferred")
        elif market_cap is None:
            if log_market_cap_warning:
                logger.warning(f"[Liquidity] {ticker}: market cap unavailable")
            reasons.append("market cap unavailable")
        elif market_cap < V2_MIN_MARKET_CAP:
            reject_reasons.append(f"market cap < {V2_MIN_MARKET_CAP}")
        else:
            reasons.append("market cap passed")

        passed = not reject_reasons
        return {
            "passed": passed,
            "score": 10 if passed else 0,
            "reasons": reasons,
            "reject_reasons": reject_reasons,
        }
    except Exception as e:
        logger.error(f"[Liquidity] Evaluation failed: {e}", exc_info=True)
        return {
            "passed": False,
            "score": 0,
            "reasons": [],
            "reject_reasons": [f"liquidity evaluation failed: {type(e).__name__}"],
        }


def fetch_ticker_metadata(ticker: str, log_warnings: bool = True) -> dict:
    """Best-effort yfinance metadata lookup for market cap and sector."""
    try:
        configure_yfinance_cache()
        info = yf.Ticker(ticker).info or {}
        return {
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
        }
    except Exception as e:
        if log_warnings:
            logger.warning(f"[Liquidity] {ticker}: metadata fetch failed: {type(e).__name__}: {e}")
        return {"market_cap": None, "sector": None}


def enrich_with_market_metadata(
    data: dict,
    fetch_metadata: bool = True,
    log_warnings: bool = True,
) -> dict:
    """Return a snapshot copy with optional yfinance market cap and sector fields."""
    try:
        ticker = str(data.get("ticker", ""))
        metadata = (
            fetch_ticker_metadata(ticker, log_warnings=log_warnings)
            if ticker and fetch_metadata
            else {"market_cap": None, "sector": None}
        )
        enriched = {**data}
        enriched.setdefault("market_cap", metadata.get("market_cap"))
        enriched.setdefault("sector", metadata.get("sector"))
        return enriched
    except Exception as e:
        if log_warnings:
            logger.error(f"[Liquidity] Metadata enrichment failed: {e}", exc_info=True)
        return {**data, "market_cap": data.get("market_cap"), "sector": data.get("sector")}
