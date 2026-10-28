"""
Tests for the data storage layer (data_storage.py).
"""

from __future__ import annotations

import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pandas as pd

from config import StorageConfig
from data_storage import CSVStorage, SQLiteStorage, StorageError


# ──────────────────────────────────────────────────────────────────────
# CSV Storage
# ──────────────────────────────────────────────────────────────────────


class TestCSVStorage:
    """Tests for CSVStorage."""

    def test_save_creates_csv(self, tmp_output_dir):
        """save() should create a CSV file with correct content."""
        cfg = StorageConfig(output_dir=tmp_output_dir)
        storage = CSVStorage(cfg)

        df = pd.DataFrame([
            {"symbol": "TCS", "ltp": 3500.0},
            {"symbol": "INFY", "ltp": 1500.0},
        ])
        path = storage.save(df, "test-dataset", "2026-10-28")

        assert os.path.exists(path)
        assert "test-dataset_2026-10-28.csv" in path

        # Read it back and verify
        loaded = pd.read_csv(path)
        assert len(loaded) == 2
        assert list(loaded.columns) == ["symbol", "ltp"]

    def test_same_day_overwrite(self, tmp_output_dir):
        """Running twice for the same date should overwrite, not duplicate."""
        cfg = StorageConfig(output_dir=tmp_output_dir)
        storage = CSVStorage(cfg)

        df1 = pd.DataFrame([{"symbol": "A", "ltp": 100}])
        df2 = pd.DataFrame([{"symbol": "B", "ltp": 200}, {"symbol": "C", "ltp": 300}])

        path1 = storage.save(df1, "overwrite-test", "2026-10-28")
        path2 = storage.save(df2, "overwrite-test", "2026-10-28")

        # Same file path
        assert path1 == path2

        # Content should be the second write
        loaded = pd.read_csv(path2)
        assert len(loaded) == 2
        assert loaded["symbol"].tolist() == ["B", "C"]

    def test_different_dates_create_separate_files(self, tmp_output_dir):
        """Different dates should produce separate files."""
        cfg = StorageConfig(output_dir=tmp_output_dir)
        storage = CSVStorage(cfg)

        df = pd.DataFrame([{"symbol": "X", "ltp": 50}])
        path1 = storage.save(df, "multi-date", "2026-10-27")
        path2 = storage.save(df, "multi-date", "2026-10-28")

        assert path1 != path2
        assert os.path.exists(path1)
        assert os.path.exists(path2)

    def test_output_dir_created_automatically(self, tmp_path):
        """The output directory should be created if it doesn't exist."""
        new_dir = str(tmp_path / "new_output")
        assert not os.path.exists(new_dir)

        cfg = StorageConfig(output_dir=new_dir)
        CSVStorage(cfg)

        assert os.path.isdir(new_dir)

    def test_empty_dataframe_creates_header_only_csv(self, tmp_output_dir):
        """An empty DataFrame should still produce a valid CSV (header only)."""
        cfg = StorageConfig(output_dir=tmp_output_dir)
        storage = CSVStorage(cfg)

        df = pd.DataFrame(columns=["symbol", "ltp"])
        path = storage.save(df, "empty-test", "2026-10-28")

        loaded = pd.read_csv(path)
        assert len(loaded) == 0
        assert list(loaded.columns) == ["symbol", "ltp"]


# ──────────────────────────────────────────────────────────────────────
# SQLite Storage
# ──────────────────────────────────────────────────────────────────────


class TestSQLiteStorage:
    """Tests for SQLiteStorage."""

    def test_save_creates_table(self, tmp_output_dir):
        """First save should create the table and insert rows."""
        storage = SQLiteStorage(tmp_output_dir)
        df = pd.DataFrame([
            {"symbol": "TCS", "ltp": 3500.0},
            {"symbol": "INFY", "ltp": 1500.0},
        ])
        count = storage.save(df, "test-table", "2026-10-28")
        assert count == 2

        # Verify in SQLite
        db_path = os.path.join(tmp_output_dir, "nse_market_data.db")
        with sqlite3.connect(db_path) as conn:
            result = pd.read_sql("SELECT * FROM test_table", conn)
        assert len(result) == 2
        assert "download_date" in result.columns

    def test_same_date_replaces_records(self, tmp_output_dir):
        """Re-saving for the same date should replace, not append."""
        storage = SQLiteStorage(tmp_output_dir)

        df1 = pd.DataFrame([{"symbol": "A", "ltp": 100}])
        storage.save(df1, "replace-test", "2026-10-28")

        df2 = pd.DataFrame([{"symbol": "B", "ltp": 200}, {"symbol": "C", "ltp": 300}])
        storage.save(df2, "replace-test", "2026-10-28")

        db_path = os.path.join(tmp_output_dir, "nse_market_data.db")
        with sqlite3.connect(db_path) as conn:
            result = pd.read_sql(
                "SELECT * FROM replace_test WHERE download_date='2026-10-28'", conn
            )
        assert len(result) == 2

    def test_different_dates_accumulate(self, tmp_output_dir):
        """Different dates should accumulate in the table."""
        storage = SQLiteStorage(tmp_output_dir)

        df = pd.DataFrame([{"symbol": "X", "ltp": 50}])
        storage.save(df, "history-test", "2026-10-27")
        storage.save(df, "history-test", "2026-10-28")

        db_path = os.path.join(tmp_output_dir, "nse_market_data.db")
        with sqlite3.connect(db_path) as conn:
            result = pd.read_sql("SELECT * FROM history_test", conn)
        assert len(result) == 2
