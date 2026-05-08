# logging_config.py — Shared logging setup for every entry point.
# Fix #18 — rotate daily; keep 14 days of history so yesterday's run is
# diagnosable even if stdout was lost.
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler


def setup_logging(log_filename: str = "signal_bot.log") -> None:
    """
    Configure root logger with stdout + daily-rotating file handler.
    Idempotent: callers can invoke this multiple times safely.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    log_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), log_filename
    )
    file_handler = TimedRotatingFileHandler(
        log_path, when="D", backupCount=14, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    root.setLevel(logging.INFO)
