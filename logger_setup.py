"""
Logging setup for NSE Market Data Downloader.

Provides a centralized, configurable logging system with both
console and rotating-file handlers.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from config import LOG_DIR, LOG_FORMAT, LOG_DATE_FORMAT, LOG_FILE


_initialized = False


def setup_logging(
    level: int = logging.INFO,
    log_dir: Optional[str] = None,
) -> logging.Logger:
    """
    Configure the root logger for the application.

    Parameters
    ----------
    level : int
        Logging level (default INFO).
    log_dir : str, optional
        Override the default log directory.

    Returns
    -------
    logging.Logger
        The configured root logger.
    """
    global _initialized
    if _initialized:
        return logging.getLogger("nse_downloader")

    log_directory = log_dir or LOG_DIR
    os.makedirs(log_directory, exist_ok=True)

    logger = logging.getLogger("nse_downloader")
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # ── Console handler ──────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── Rotating file handler (5 MB × 3 backups) ────────────────────
    log_path = os.path.join(log_directory, LOG_FILE)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _initialized = True
    logger.info("Logging initialised — file: %s", log_path)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the application namespace."""
    return logging.getLogger(f"nse_downloader.{name}")
