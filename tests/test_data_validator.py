"""
Tests for the data validation layer (data_validator.py).
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd

from config import DATASETS
from data_validator import DataValidator, ValidationError
from tests.conftest import (
    make_gainers_response,
    make_band_hitters_response,
    make_volume_gainers_response,
    make_52week_response,
    SAMPLE_RESPONSES,
)


# ──────────────────────────────────────────────────────────────────────
# extract_records
# ──────────────────────────────────────────────────────────────────────


class TestExtractRecords:
    """Tests for DataValidator.extract_records."""

    @pytest.mark.parametrize("key", list(DATASETS.keys()))
    def test_extract_from_valid_response(self, key):
        """Each sample response should yield a non-empty list."""
        ds = DATASETS[key]
        raw = SAMPLE_RESPONSES[key]
        records = DataValidator.extract_records(raw, ds)
        assert isinstance(records, list)
        assert len(records) > 0

    def test_extract_from_empty_dict(self):
        """An empty JSON dict should raise ValidationError."""
        ds = DATASETS["top-gainers-losers"]
        with pytest.raises(ValidationError, match="No usable data"):
            DataValidator.extract_records({}, ds)

    def test_extract_from_non_dict(self):
        """A non-dict JSON root should raise ValidationError."""
        ds = DATASETS["upper-band-hitters"]
        with pytest.raises(ValidationError, match="Expected a JSON object"):
            DataValidator.extract_records(["not", "a", "dict"], ds)

    def test_extract_empty_list_raises(self):
        """A key mapping to an empty list should not match."""
        ds = DATASETS["volume-gainers-spurts"]
        with pytest.raises(ValidationError, match="No usable data"):
            DataValidator.extract_records({"data": []}, ds)

    def test_fallback_key_resolution(self):
        """If the primary key is missing, fallback keys should be tried."""
        ds = DATASETS["top-gainers-losers"]
        # The config expects "NIFTY" but we provide data under "allSec"
        raw = {"allSec": [{"symbol": "TEST"}]}
        records = DataValidator.extract_records(raw, ds)
        assert len(records) == 1


# ──────────────────────────────────────────────────────────────────────
# validate_columns
# ──────────────────────────────────────────────────────────────────────


class TestValidateColumns:
    """Tests for DataValidator.validate_columns."""

    def test_all_columns_present(self):
        """No missing columns when the schema matches."""
        ds = DATASETS["top-gainers-losers"]
        df = pd.DataFrame(make_gainers_response()["NIFTY"])
        passed, missing = DataValidator.validate_columns(df, ds)
        assert passed is True
        assert missing == []

    def test_missing_columns_detected(self):
        """Missing columns should be reported."""
        ds = DATASETS["52-week-high"]
        df = pd.DataFrame([{"symbol": "ABC", "ltp": 100}])
        passed, missing = DataValidator.validate_columns(df, ds)
        assert passed is False
        assert "highLowPrice" in missing


# ──────────────────────────────────────────────────────────────────────
# remove_duplicates
# ──────────────────────────────────────────────────────────────────────


class TestRemoveDuplicates:
    """Tests for DataValidator.remove_duplicates."""

    def test_no_duplicates(self):
        """Unique rows should pass through unchanged."""
        ds = DATASETS["upper-band-hitters"]
        df = pd.DataFrame(make_band_hitters_response()["data"])
        result = DataValidator.remove_duplicates(df, ds)
        assert len(result) == len(df)

    def test_duplicates_removed(self):
        """Exact duplicate rows should be dropped."""
        ds = DATASETS["volume-gainers-spurts"]
        raw = make_volume_gainers_response()["data"]
        raw_with_dups = raw + [raw[0]]  # duplicate the first record
        df = pd.DataFrame(raw_with_dups)
        result = DataValidator.remove_duplicates(df, ds)
        assert len(result) == len(raw)


# ──────────────────────────────────────────────────────────────────────
# validate_dataframe (integration of all checks)
# ──────────────────────────────────────────────────────────────────────


class TestValidateDataFrame:
    """Tests for DataValidator.validate_dataframe."""

    @pytest.mark.parametrize("key", list(DATASETS.keys()))
    def test_valid_dataframe_passes(self, key):
        """Valid sample data should pass validation."""
        ds = DATASETS[key]
        raw = SAMPLE_RESPONSES[key]
        records = DataValidator.extract_records(raw, ds)
        df = pd.DataFrame(records)
        result = DataValidator.validate_dataframe(df, ds, strict=False)
        assert len(result) > 0

    def test_empty_dataframe_raises(self):
        """An empty DataFrame should raise ValidationError."""
        ds = DATASETS["top-gainers-losers"]
        df = pd.DataFrame()
        with pytest.raises(ValidationError, match="empty"):
            DataValidator.validate_dataframe(df, ds)

    def test_strict_mode_raises_on_missing_columns(self):
        """In strict mode, missing expected columns should raise."""
        ds = DATASETS["52-week-high"]
        df = pd.DataFrame([{"symbol": "TEST", "ltp": 99}])
        with pytest.raises(ValidationError, match="Missing required columns"):
            DataValidator.validate_dataframe(df, ds, strict=True)

    def test_non_strict_mode_warns_but_passes(self):
        """In non-strict mode, missing columns are logged but data passes."""
        ds = DATASETS["52-week-high"]
        df = pd.DataFrame([{"symbol": "TEST", "ltp": 99}])
        result = DataValidator.validate_dataframe(df, ds, strict=False)
        assert len(result) == 1
