"""
Data storage layer for NSE Market Data Downloader.

Responsible for:
  • Writing validated DataFrames to CSV
  • Managing output directories
  • Handling same-day duplicate files (overwrite in place)
  • Optional SQLite storage for historical tracking
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd

from config import StorageConfig
from logger_setup import get_logger

logger = get_logger("storage")


class StorageError(Exception):
    """Raised when a file-system or database write fails."""


class CSVStorage:
    """
    Writes DataFrames to date-stamped CSV files.

    The filename template ``{dataset_key}_{date}.csv`` ensures that
    re-running on the same trading day overwrites the earlier file
    rather than creating confusing duplicates.
    """

    def __init__(self, storage_config: Optional[StorageConfig] = None) -> None:
        self._cfg = storage_config or StorageConfig()
        os.makedirs(self._cfg.output_dir, exist_ok=True)
        logger.info("CSV output directory: %s", self._cfg.output_dir)

    def save(
        self,
        df: pd.DataFrame,
        dataset_key: str,
        date_str: Optional[str] = None,
    ) -> str:
        """
        Persist *df* as a CSV file.

        Parameters
        ----------
        df : pd.DataFrame
            Validated data to store.
        dataset_key : str
            Slug used in the filename (e.g. ``top-gainers-losers``).
        date_str : str, optional
            Date stamp for the filename.  Defaults to today.

        Returns
        -------
        str
            Absolute path to the saved CSV file.
        """
        if date_str is None:
            date_str = datetime.now().strftime(self._cfg.csv_date_format)

        filepath = self._cfg.get_filepath(dataset_key, date_str)

        if os.path.exists(filepath):
            logger.info(
                "Overwriting existing file for same-day run: %s", filepath,
            )

        try:
            df.to_csv(filepath, index=False, encoding=self._cfg.csv_encoding)
            logger.info(
                "Saved %d records → %s (%.1f KB)",
                len(df),
                filepath,
                os.path.getsize(filepath) / 1024,
            )
            return filepath
        except OSError as exc:
            logger.error("Failed to write CSV: %s", exc)
            raise StorageError(f"Could not write {filepath}: {exc}") from exc


class SQLiteStorage:
    """
    Optional historical storage in a local SQLite database.

    Each dataset gets its own table.  A ``download_date`` column is added
    so that multiple days can coexist.
    """

    DB_FILENAME = "nse_market_data.db"

    def __init__(self, output_dir: str) -> None:
        self._db_path = os.path.join(output_dir, self.DB_FILENAME)
        logger.info("SQLite database: %s", self._db_path)

    def save(
        self,
        df: pd.DataFrame,
        table_name: str,
        date_str: Optional[str] = None,
    ) -> int:
        """
        Upsert *df* into the given *table_name*.

        Returns the number of rows written.
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # Sanitise table name for SQL
        safe_table = table_name.replace("-", "_")
        df = df.copy()
        df["download_date"] = date_str

        try:
            with sqlite3.connect(self._db_path) as conn:
                # Remove existing records for the same date
                conn.execute(
                    f"DELETE FROM [{safe_table}] WHERE download_date = ?",
                    (date_str,),
                )
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet — will be created below

        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = df.to_sql(
                    safe_table,
                    conn,
                    if_exists="append",
                    index=False,
                )
                logger.info(
                    "SQLite: wrote %d rows to table '%s' for date %s.",
                    len(df), safe_table, date_str,
                )
                return len(df)
        except Exception as exc:
            logger.error("SQLite write failed: %s", exc)
            raise StorageError(
                f"Could not write to SQLite table '{safe_table}': {exc}"
            ) from exc
