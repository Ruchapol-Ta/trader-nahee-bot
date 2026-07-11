# universe.py — Load stock universes.
#
# Fix #2 — core sources (S&P 500, Nasdaq 100) raise UniverseLoadError when
#   they return a clearly-broken list. The bot then surfaces a Telegram alert
#   and bails, instead of silently scanning a crippled subset.
# Also: pruned known-delisted names from the Russell sample.
import logging
from io import StringIO

import pandas as pd
import requests

from config import EXPECTED_MIN_SP500, EXPECTED_MIN_NASDAQ

logger = logging.getLogger(__name__)


class UniverseLoadError(RuntimeError):
    """Raised when a ticker source returns too few tickers to trust."""


# Wikipedia rejects pandas' default UA with HTTP 403.
_WIKI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
_NASDAQ_100_WIKIPEDIA_URL = (
    "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
)


def dedupe_tickers(*ticker_lists: list[str]) -> list[str]:
    """Normalize, dedupe, and sort ticker lists for Yahoo Finance symbols."""
    try:
        deduped: set[str] = set()
        for ticker_list in ticker_lists:
            for ticker in ticker_list:
                normalized = str(ticker).strip().replace(".", "-")
                if normalized:
                    deduped.add(normalized)
        return sorted(deduped)
    except Exception as e:
        logger.error(f"[Universe] Ticker dedupe failed: {e}", exc_info=True)
        return []


def _fetch_wiki_tables(url: str) -> list[pd.DataFrame]:
    resp = requests.get(url, headers=_WIKI_HEADERS, timeout=15)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def get_sp500_tickers() -> list[str]:
    """Fetch S&P 500 tickers from Wikipedia. Raises UniverseLoadError on bad data."""
    try:
        tables = _fetch_wiki_tables(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )
        tickers = [t.replace(".", "-") for t in tables[0]["Symbol"].tolist()]
    except Exception as e:
        raise UniverseLoadError(f"S&P 500 fetch failed: {type(e).__name__}: {e}") from e

    if len(tickers) < EXPECTED_MIN_SP500:
        raise UniverseLoadError(
            f"S&P 500 returned only {len(tickers)} tickers "
            f"(expected ≥ {EXPECTED_MIN_SP500})"
        )
    logger.info(f"[Universe] S&P 500: {len(tickers)} tickers loaded")
    return tickers


def get_nasdaq100_tickers() -> list[str]:
    """Fetch Nasdaq 100 tickers from Wikipedia. Raises UniverseLoadError on bad data."""
    try:
        tables = _fetch_wiki_tables(_NASDAQ_100_WIKIPEDIA_URL)
    except Exception as e:
        raise UniverseLoadError(f"Nasdaq 100 fetch failed: {type(e).__name__}: {e}") from e

    for table in tables:
        if "Ticker" in table.columns:
            tickers = table["Ticker"].tolist()
            if len(tickers) < EXPECTED_MIN_NASDAQ:
                raise UniverseLoadError(
                    f"Nasdaq 100 returned only {len(tickers)} tickers "
                    f"(expected ≥ {EXPECTED_MIN_NASDAQ})"
                )
            logger.info(f"[Universe] Nasdaq 100: {len(tickers)} tickers loaded")
            return tickers

    raise UniverseLoadError("Nasdaq 100: 'Ticker' column not found in any table")


def get_russell2000_tickers() -> list[str]:
    """
    Curated liquid Russell 2000 subset. Static list — refresh periodically.
    Previously-delisted symbols (CIVI, EPAY, ESTE, HTLF, MNRL, PAYA, PDCE,
    SBOW, SWN, UCBI, VTLE) have been removed.
    """
    RUSSELL_SAMPLE = [
        "IOVA", "ARWR", "PRAX", "ACAD", "INVA", "FLNC", "BLDR", "ATKR",
        "MYRG", "AEIS", "ENVA", "CARG", "SAIA", "ABCB", "WTFC", "SFNC",
        "IBOC", "NBTB", "STBA", "TCBI", "CVBF", "WSFS", "BANF", "BOKF",
        "CUBI", "TBBK", "FFIN", "HOPE", "GBCI", "FULT", "PNFP", "RNST",
        "HOMB", "WAFD", "SBCF", "NWBI", "EVTC", "BPOP",
        "CWEN", "AROC", "PUMP", "NINE", "KLXE",
        "SGU", "TRGP", "CHRD", "REX", "GRNT",
        "CRGY", "MTDR", "HPK", "ARIS", "NOG", "SM", "BATL",
        "PGNY", "ACLS", "FORM", "AAON", "AEHR", "ICHR", "ONTO", "LRCX",
        "MKSI", "NTCT", "DIOD", "CEVA", "AMBA", "AIOT", "OSIS", "SMTC",
        "MTSI", "COHU", "RMBS", "POWI", "NTGR", "BHE", "VICR", "PDFS",
        "PRGS", "PLUS", "EGHT", "AMSF", "HCKT", "JKHY", "CCSI", "TTEC",
        "BRZE", "ALRM", "ARLO", "LSPD", "TASK", "WEAV",
    ]
    logger.info(f"[Universe] Russell 2000 sample: {len(RUSSELL_SAMPLE)} tickers loaded")
    return RUSSELL_SAMPLE


def get_full_universe() -> list[str]:
    """
    Combine all three universes, dedupe, sort. Raises UniverseLoadError if
    any core source (S&P 500 / Nasdaq 100) falls below its sanity threshold.
    """
    sp500 = get_sp500_tickers()
    ndx100 = get_nasdaq100_tickers()
    rut2000 = get_russell2000_tickers()
    combined = dedupe_tickers(sp500, ndx100, rut2000)
    logger.info(f"[Universe] Full universe: {len(combined)} unique tickers")
    return combined


def get_v2_universe() -> list[str]:
    """Load the V2 production universe: S&P 500 plus Nasdaq 100, deduped."""
    try:
        sp500 = get_sp500_tickers()
        ndx100 = get_nasdaq100_tickers()
        combined = dedupe_tickers(sp500, ndx100)
        logger.info(f"[Universe] V2 universe: {len(combined)} unique tickers")
        return combined
    except UniverseLoadError:
        raise
    except Exception as e:
        raise UniverseLoadError(f"V2 universe load failed: {type(e).__name__}: {e}") from e
