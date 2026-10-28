"""
Tests for the pipeline orchestrator and CLI entry point.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
import pytest
import pandas as pd

from config import DATASETS, HTTPConfig, StorageConfig
from pipeline import Pipeline, DownloadResult, PipelineReport
from nse_client import NSEClientError, APIRequestError
from data_validator import ValidationError
from tests.conftest import SAMPLE_RESPONSES


# ──────────────────────────────────────────────────────────────────────
# Pipeline — unit tests with mocked client
# ──────────────────────────────────────────────────────────────────────


class TestPipeline:
    """Tests for the Pipeline orchestrator."""

    def _mock_client_factory(self, responses: dict | None = None):
        """Build a mock NSEClient that returns canned responses."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        if responses is None:
            responses = SAMPLE_RESPONSES

        def side_effect(ds_config):
            key = ds_config.key
            if key in responses:
                return responses[key]
            raise APIRequestError(f"No canned response for {key}")

        mock_client.fetch_dataset.side_effect = side_effect
        return mock_client

    @patch("pipeline.NSEClient")
    def test_all_datasets_succeed(self, mock_client_cls, tmp_output_dir):
        """All four datasets should succeed with valid responses."""
        mock_client_cls.return_value = self._mock_client_factory()

        pipeline = Pipeline(
            http_config=HTTPConfig(inter_request_delay=0),
            storage_config=StorageConfig(output_dir=tmp_output_dir),
        )
        report = pipeline.run(date_str="2026-10-28")

        assert report.succeeded == 4
        assert report.failed == 0
        assert len(report.results) == 4

        # All four CSV files should exist
        for result in report.results:
            assert result.success
            assert result.filepath is not None
            assert os.path.exists(result.filepath)
            assert result.record_count > 0

    @patch("pipeline.NSEClient")
    def test_single_dataset(self, mock_client_cls, tmp_output_dir):
        """Requesting a single dataset should produce one CSV."""
        mock_client_cls.return_value = self._mock_client_factory()

        pipeline = Pipeline(
            http_config=HTTPConfig(inter_request_delay=0),
            storage_config=StorageConfig(output_dir=tmp_output_dir),
        )
        report = pipeline.run(
            dataset_keys=["52-week-high"], date_str="2026-10-28"
        )

        assert len(report.results) == 1
        assert report.succeeded == 1
        assert report.results[0].dataset_key == "52-week-high"

    @patch("pipeline.NSEClient")
    def test_partial_failure_continues(self, mock_client_cls, tmp_output_dir):
        """If one dataset fails, the others should still be processed."""
        partial_responses = dict(SAMPLE_RESPONSES)
        del partial_responses["upper-band-hitters"]  # this one will fail

        mock_client = self._mock_client_factory(partial_responses)
        mock_client_cls.return_value = mock_client

        pipeline = Pipeline(
            http_config=HTTPConfig(inter_request_delay=0),
            storage_config=StorageConfig(output_dir=tmp_output_dir),
        )
        report = pipeline.run(date_str="2026-10-28")

        assert report.succeeded == 3
        assert report.failed == 1

        failed = [r for r in report.results if not r.success]
        assert failed[0].dataset_key == "upper-band-hitters"

    @patch("pipeline.NSEClient")
    def test_all_datasets_fail(self, mock_client_cls, tmp_output_dir):
        """If all datasets fail, report should reflect that."""
        mock_client = self._mock_client_factory({})  # empty = all fail
        mock_client_cls.return_value = mock_client

        pipeline = Pipeline(
            http_config=HTTPConfig(inter_request_delay=0),
            storage_config=StorageConfig(output_dir=tmp_output_dir),
        )
        report = pipeline.run(date_str="2026-10-28")

        assert report.succeeded == 0
        assert report.failed == 4

    def test_invalid_dataset_key_raises(self, tmp_output_dir):
        """An unknown dataset key should raise ValueError."""
        pipeline = Pipeline(
            storage_config=StorageConfig(output_dir=tmp_output_dir),
        )
        with pytest.raises(ValueError, match="Unknown dataset key"):
            pipeline.run(dataset_keys=["nonexistent-dataset"])


# ──────────────────────────────────────────────────────────────────────
# DownloadResult / PipelineReport
# ──────────────────────────────────────────────────────────────────────


class TestPipelineReport:
    """Tests for the report data classes."""

    def test_report_summary_format(self):
        """The summary string should contain key information."""
        report = PipelineReport(
            started_at="2026-10-28T10:00:00",
            finished_at="2026-10-28T10:01:00",
            results=[
                DownloadResult("a", "Dataset A", True, "/a.csv", 10),
                DownloadResult("b", "Dataset B", False, error="timeout"),
            ],
        )

        summary = report.summary()
        assert "OK: 1" in summary
        assert "FAILED: 1" in summary
        assert "Dataset A" in summary
        assert "timeout" in summary

    def test_report_succeeded_count(self):
        report = PipelineReport(
            results=[
                DownloadResult("a", "A", True),
                DownloadResult("b", "B", True),
                DownloadResult("c", "C", False),
            ]
        )
        assert report.succeeded == 2
        assert report.failed == 1


# ──────────────────────────────────────────────────────────────────────
# CLI (main.py) tests
# ──────────────────────────────────────────────────────────────────────


class TestCLI:
    """Tests for the main.py CLI entry point."""

    def test_list_datasets(self, capsys):
        from main import main

        exit_code = main(["--list"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "top-gainers-losers" in captured.out
        assert "52-week-high" in captured.out

    @patch("main.Pipeline")
    def test_cli_all_datasets(self, mock_pipeline_cls, tmp_output_dir):
        from main import main

        mock_report = PipelineReport(
            started_at="now",
            finished_at="now",
            results=[
                DownloadResult(k, DATASETS[k].name, True, f"/out/{k}.csv", 5)
                for k in DATASETS
            ],
        )
        mock_pipeline_cls.return_value.run.return_value = mock_report

        exit_code = main(["--output-dir", tmp_output_dir])
        assert exit_code == 0

    @patch("main.Pipeline")
    def test_cli_single_dataset(self, mock_pipeline_cls, tmp_output_dir):
        from main import main

        mock_report = PipelineReport(
            started_at="now",
            finished_at="now",
            results=[
                DownloadResult("52-week-high", "52-Week High", True, "/x.csv", 3)
            ],
        )
        mock_pipeline_cls.return_value.run.return_value = mock_report

        exit_code = main([
            "--dataset", "52-week-high", "--output-dir", tmp_output_dir
        ])
        assert exit_code == 0

    @patch("main.Pipeline")
    def test_cli_returns_1_on_failures(self, mock_pipeline_cls, tmp_output_dir):
        from main import main

        mock_report = PipelineReport(
            started_at="now",
            finished_at="now",
            results=[
                DownloadResult("a", "A", False, error="fail"),
            ],
        )
        mock_pipeline_cls.return_value.run.return_value = mock_report

        exit_code = main(["--output-dir", tmp_output_dir])
        assert exit_code == 1
