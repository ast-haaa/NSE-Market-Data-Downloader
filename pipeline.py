"""
Pipeline orchestrator for NSE Market Data Downloader.

Glues together the client, validator, and storage layers into a
single, fault-tolerant pipeline that processes one or more datasets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from config import DATASETS, DatasetConfig, HTTPConfig, StorageConfig
from nse_client import NSEClient, NSEClientError
from data_validator import DataValidator, ValidationError
from data_storage import CSVStorage, SQLiteStorage, StorageError
from logger_setup import get_logger

logger = get_logger("pipeline")


@dataclass
class DownloadResult:
    """Outcome of a single dataset download attempt."""

    dataset_key: str
    dataset_name: str
    success: bool
    filepath: Optional[str] = None
    record_count: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class PipelineReport:
    """Summary of the entire pipeline run."""

    started_at: str = ""
    finished_at: str = ""
    results: List[DownloadResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.success)

    def summary(self) -> str:
        lines = [
            "",
            "=" * 60,
            "  NSE Market Data Downloader — Run Report",
            "=" * 60,
            f"  Started  : {self.started_at}",
            f"  Finished : {self.finished_at}",
            f"  Total    : {len(self.results)}  |  "
            f"OK: {self.succeeded}  |  FAILED: {self.failed}",
            "-" * 60,
        ]
        for r in self.results:
            status = "✓" if r.success else "✗"
            info = (
                f"{r.record_count} records → {r.filepath}"
                if r.success
                else f"ERROR: {r.error}"
            )
            lines.append(f"  {status}  {r.dataset_name:36s} | {info}")
        lines.append("=" * 60)
        return "\n".join(lines)


class Pipeline:
    """
    Orchestrates data acquisition → validation → storage for one or
    more NSE datasets.

    Example::

        pipeline = Pipeline()
        report = pipeline.run()               # all datasets
        report = pipeline.run(["52-week-high"])  # single dataset
    """

    def __init__(
        self,
        http_config: Optional[HTTPConfig] = None,
        storage_config: Optional[StorageConfig] = None,
        use_sqlite: bool = False,
    ) -> None:
        self._http_cfg = http_config or HTTPConfig()
        self._storage_cfg = storage_config or StorageConfig()
        self._use_sqlite = use_sqlite
        self._validator = DataValidator()
        self._csv_storage = CSVStorage(self._storage_cfg)
        self._sqlite_storage: Optional[SQLiteStorage] = None
        if use_sqlite:
            self._sqlite_storage = SQLiteStorage(self._storage_cfg.output_dir)

    # ── public API ───────────────────────────────────────────────────

    def run(
        self,
        dataset_keys: Optional[List[str]] = None,
        date_str: Optional[str] = None,
    ) -> PipelineReport:
        """
        Execute the pipeline for the requested datasets.

        Parameters
        ----------
        dataset_keys : list of str, optional
            Which datasets to download.  ``None`` means all.
        date_str : str, optional
            Override date stamp for filenames.

        Returns
        -------
        PipelineReport
        """
        if date_str is None:
            date_str = datetime.now().strftime(self._storage_cfg.csv_date_format)

        targets = self._resolve_targets(dataset_keys)
        report = PipelineReport(
            started_at=datetime.now().isoformat(timespec="seconds"),
        )

        logger.info(
            "Pipeline started — %d dataset(s) targeted for %s.",
            len(targets), date_str,
        )

        with NSEClient(self._http_cfg) as client:
            for ds_config in targets:
                result = self._process_dataset(client, ds_config, date_str)
                report.results.append(result)

        report.finished_at = datetime.now().isoformat(timespec="seconds")
        logger.info(report.summary())
        return report

    # ── private helpers ──────────────────────────────────────────────

    def _resolve_targets(
        self, keys: Optional[List[str]]
    ) -> List[DatasetConfig]:
        """Map CLI keys to DatasetConfig objects."""
        if keys is None:
            return list(DATASETS.values())

        targets: List[DatasetConfig] = []
        for key in keys:
            if key not in DATASETS:
                logger.error("Unknown dataset key: '%s'", key)
                raise ValueError(
                    f"Unknown dataset key '{key}'. "
                    f"Valid keys: {list(DATASETS.keys())}"
                )
            targets.append(DATASETS[key])
        return targets

    def _process_dataset(
        self,
        client: NSEClient,
        ds_config: DatasetConfig,
        date_str: str,
    ) -> DownloadResult:
        """Fetch → validate → store a single dataset."""
        t0 = time.monotonic()
        result = DownloadResult(
            dataset_key=ds_config.key,
            dataset_name=ds_config.name,
            success=False,
        )

        try:
            # 1. Acquire
            raw_json = client.fetch_dataset(ds_config)

            # 2. Extract records from the JSON envelope
            records = self._validator.extract_records(raw_json, ds_config)

            # 3. Build DataFrame and validate
            df = pd.DataFrame(records)
            df = self._validator.validate_dataframe(df, ds_config, strict=False)

            # 4. Persist to CSV
            filepath = self._csv_storage.save(df, ds_config.key, date_str)

            # 5. Optional SQLite
            if self._sqlite_storage:
                self._sqlite_storage.save(df, ds_config.key, date_str)

            result.success = True
            result.filepath = filepath
            result.record_count = len(df)

        except (NSEClientError, ValidationError, StorageError) as exc:
            result.error = str(exc)
            logger.error(
                "Dataset '%s' failed: %s", ds_config.name, exc,
            )
        except Exception as exc:
            result.error = f"Unexpected error: {exc}"
            logger.exception(
                "Unexpected error processing '%s'.", ds_config.name,
            )

        result.duration_seconds = round(time.monotonic() - t0, 2)
        return result
