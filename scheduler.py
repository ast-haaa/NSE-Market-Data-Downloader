"""
Scheduler for automated/recurring NSE data downloads.

Provides a simple cron-like scheduler using the standard library
(no external dependencies like APScheduler required).
"""

from __future__ import annotations

import sched
import time
import threading
from datetime import datetime
from typing import List, Optional

from config import HTTPConfig, StorageConfig
from pipeline import Pipeline
from logger_setup import get_logger

logger = get_logger("scheduler")


class Scheduler:
    """
    Run the download pipeline on a fixed interval.

    Usage::

        scheduler = Scheduler(interval_seconds=3600)  # every hour
        scheduler.start()                              # blocks
    """

    def __init__(
        self,
        interval_seconds: int = 3600,
        dataset_keys: Optional[List[str]] = None,
        http_config: Optional[HTTPConfig] = None,
        storage_config: Optional[StorageConfig] = None,
        use_sqlite: bool = False,
    ) -> None:
        self._interval = interval_seconds
        self._dataset_keys = dataset_keys
        self._http_cfg = http_config or HTTPConfig()
        self._storage_cfg = storage_config or StorageConfig()
        self._use_sqlite = use_sqlite
        self._running = False

    def start(self) -> None:
        """Start the scheduler loop (blocks the calling thread)."""
        self._running = True
        logger.info(
            "Scheduler started — interval: %ds, datasets: %s",
            self._interval,
            self._dataset_keys or "ALL",
        )

        while self._running:
            self._execute()
            logger.info(
                "Next run in %d seconds (at %s).",
                self._interval,
                datetime.now().isoformat(timespec="seconds"),
            )
            time.sleep(self._interval)

    def stop(self) -> None:
        """Signal the scheduler to stop after the current iteration."""
        self._running = False
        logger.info("Scheduler stop requested.")

    def _execute(self) -> None:
        """Run a single pipeline iteration."""
        logger.info("Scheduled run starting at %s", datetime.now().isoformat())
        try:
            pipeline = Pipeline(
                http_config=self._http_cfg,
                storage_config=self._storage_cfg,
                use_sqlite=self._use_sqlite,
            )
            report = pipeline.run(dataset_keys=self._dataset_keys)
            print(report.summary())
        except Exception as exc:
            logger.exception("Scheduled run failed: %s", exc)
