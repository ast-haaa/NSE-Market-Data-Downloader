"""
Configuration module for NSE Market Data Downloader.

Keeps all dataset URLs, API endpoints, headers, and tunable parameters
separate from the application logic.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────
# NSE Base URLs
# ──────────────────────────────────────────────────────────────────────
NSE_BASE_URL = "https://www.nseindia.com"
NSE_HOME_URL = NSE_BASE_URL + "/"


# ──────────────────────────────────────────────────────────────────────
# Browser-like headers required to pass NSE's WAF (Akamai / Cloudflare)
# ──────────────────────────────────────────────────────────────────────
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": NSE_HOME_URL,
}


# ──────────────────────────────────────────────────────────────────────
# Dataset definitions
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DatasetConfig:
    """Immutable configuration for a single NSE dataset."""

    name: str                       # Human-readable name
    key: str                        # CLI key (slug)
    api_path: str                   # API path relative to NSE_BASE_URL
    page_path: str                  # Page path for referer / cookie priming
    json_data_key: str              # Top-level key inside the JSON response
    expected_columns: List[str]     # Columns that MUST be present for validation
    description: str = ""           # Optional description


DATASETS: Dict[str, DatasetConfig] = {
    "top-gainers-losers": DatasetConfig(
        name="Top Gainers & Losers",
        key="top-gainers-losers",
        api_path="/api/live-analysis-variations?index=gainers",
        page_path="/market-data/top-gainers-losers",
        json_data_key="NIFTY",
        expected_columns=[
            "symbol", "open_price", "high_price", "low_price",
            "prev_price", "ltp", "perChange",
        ],
        description="NIFTY top gainers with price and percentage change.",
    ),
    "upper-band-hitters": DatasetConfig(
        name="Upper Band Hitters",
        key="upper-band-hitters",
        api_path="/api/live-analysis-price-band-hitter",
        page_path="/market-data/upper-band-hitters",
        json_data_key="upper",
        expected_columns=["symbol", "ltp", "bandHitDate"],
        description="Securities that hit the upper price band.",
    ),
    "volume-gainers-spurts": DatasetConfig(
        name="Volume Gainers / Spurts",
        key="volume-gainers-spurts",
        api_path="/api/live-analysis-volume-gainers",
        page_path="/market-data/volume-gainers-spurts",
        json_data_key="data",
        expected_columns=["symbol", "ltp"],
        description="Securities with significant volume increases.",
    ),
    "52-week-high": DatasetConfig(
        name="52-Week High — Equity Market",
        key="52-week-high",
        api_path="/api/live-analysis-data-52weekhighstock",
        page_path="/market-data/52-week-high-equity-market",
        json_data_key="data",
        expected_columns=["symbol", "ltp", "highLowPrice"],
        description="Equities touching a new 52-week high.",
    ),
}


# ──────────────────────────────────────────────────────────────────────
# HTTP / Retry settings
# ──────────────────────────────────────────────────────────────────────
@dataclass
class HTTPConfig:
    """Tunable HTTP parameters."""

    request_timeout: int = 15           # seconds per request
    session_init_timeout: int = 10      # seconds for the initial cookie request
    max_retries: int = 3                # total attempts per request
    retry_backoff_factor: float = 1.5   # exponential backoff multiplier
    retry_status_codes: tuple = (429, 500, 502, 503, 504)
    inter_request_delay: float = 1.5    # seconds between API calls (rate limit)


# ──────────────────────────────────────────────────────────────────────
# Output / storage settings
# ──────────────────────────────────────────────────────────────────────
@dataclass
class StorageConfig:
    """File-system output configuration."""

    output_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    csv_date_format: str = "%Y-%m-%d"
    csv_encoding: str = "utf-8-sig"     # BOM for Excel compatibility
    filename_template: str = "{dataset_key}_{date}.csv"

    def get_filepath(self, dataset_key: str, date_str: str) -> str:
        """Return the full output path for a given dataset and date."""
        filename = self.filename_template.format(
            dataset_key=dataset_key, date=date_str
        )
        return os.path.join(self.output_dir, filename)


# ──────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "nse_downloader.log"
