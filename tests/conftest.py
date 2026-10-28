"""
Shared test fixtures and helpers for the NSE Market Data Downloader tests.
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any, Dict, List

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import DatasetConfig, DATASETS, HTTPConfig, StorageConfig


# ──────────────────────────────────────────────────────────────────────
# Reusable sample data factories
# ──────────────────────────────────────────────────────────────────────

def make_gainers_response(n: int = 3) -> Dict[str, Any]:
    """Return a realistic top-gainers JSON response with *n* records."""
    records = [
        {
            "symbol": f"STOCK{i}",
            "series": "EQ",
            "open_price": 100.0 + i,
            "high_price": 110.0 + i,
            "low_price": 95.0 + i,
            "prev_price": 98.0 + i,
            "ltp": 108.0 + i,
            "perChange": round(5.0 + i * 0.5, 2),
            "trade_quantity": 10000 * (i + 1),
        }
        for i in range(n)
    ]
    return {"NIFTY": records, "allSec": records}


def make_band_hitters_response(n: int = 3) -> Dict[str, Any]:
    """Return a realistic upper-band-hitters JSON response."""
    records = [
        {
            "symbol": f"BAND{i}",
            "series": "EQ",
            "ltp": 200.0 + i * 10,
            "open": 195.0 + i * 10,
            "high": 205.0 + i * 10,
            "low": 194.0 + i * 10,
            "prevClose": 190.0 + i * 10,
            "bandHitDate": "28-Oct-2026",
            "quantity": 5000 * (i + 1),
        }
        for i in range(n)
    ]
    return {"data": records}


def make_volume_gainers_response(n: int = 3) -> Dict[str, Any]:
    """Return a realistic volume-gainers JSON response."""
    records = [
        {
            "symbol": f"VOL{i}",
            "series": "EQ",
            "ltp": 50.0 + i * 5,
            "open": 48.0 + i * 5,
            "high": 55.0 + i * 5,
            "low": 47.0 + i * 5,
            "prevClose": 46.0 + i * 5,
            "quantity": 100000 * (i + 1),
        }
        for i in range(n)
    ]
    return {"data": records}


def make_52week_response(n: int = 3) -> Dict[str, Any]:
    """Return a realistic 52-week-high JSON response."""
    records = [
        {
            "symbol": f"HIGH{i}",
            "series": "EQ",
            "ltp": 500.0 + i * 50,
            "open": 490.0 + i * 50,
            "high": 510.0 + i * 50,
            "low": 488.0 + i * 50,
            "prevClose": 485.0 + i * 50,
            "highLowPrice": 510.0 + i * 50,
        }
        for i in range(n)
    ]
    return {"data": records}


SAMPLE_RESPONSES: Dict[str, Dict[str, Any]] = {
    "top-gainers-losers": make_gainers_response(),
    "upper-band-hitters": make_band_hitters_response(),
    "volume-gainers-spurts": make_volume_gainers_response(),
    "52-week-high": make_52week_response(),
}


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_output_dir(tmp_path):
    """Provide a clean temporary directory for CSV output."""
    output = tmp_path / "output"
    output.mkdir()
    return str(output)


@pytest.fixture
def storage_config(tmp_output_dir):
    """StorageConfig pointing to a temp directory."""
    return StorageConfig(output_dir=tmp_output_dir)


@pytest.fixture
def http_config():
    """Fast HTTP config for tests (low timeouts, single retry)."""
    return HTTPConfig(
        request_timeout=5,
        session_init_timeout=5,
        max_retries=1,
        retry_backoff_factor=0.1,
        inter_request_delay=0.0,
    )
