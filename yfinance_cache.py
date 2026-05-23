# yfinance_cache.py - repo-local yfinance cache setup.
import logging
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "py-yfinance"
_configured_cache_dir: Path | None = None


def configure_yfinance_cache(cache_dir: str | Path | None = None) -> Path | None:
    """Direct yfinance's SQLite caches to a repo-local writable folder."""
    global _configured_cache_dir

    try:
        target = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
        if not target.is_absolute():
            target = Path(__file__).resolve().parent / target
        target.mkdir(parents=True, exist_ok=True)
        resolved = target.resolve()

        if _configured_cache_dir == resolved:
            return resolved

        set_cache_location = getattr(yf, "set_tz_cache_location", None)
        if not callable(set_cache_location):
            logger.warning("[YFinanceCache] yfinance cache location API is unavailable")
            return None

        set_cache_location(str(resolved))
        _configured_cache_dir = resolved
        return resolved
    except Exception as e:
        logger.warning(f"[YFinanceCache] Cache setup failed: {type(e).__name__}: {e}")
        return None
