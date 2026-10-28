#!/usr/bin/env python3
"""
NSE Market Data Downloader — CLI entry point.

Usage
-----
Download all four datasets::

    python main.py

Download a single dataset::

    python main.py --dataset top-gainers-losers
    python main.py --dataset 52-week-high

List available datasets::

    python main.py --list

Enable SQLite storage::

    python main.py --sqlite

Custom output directory::

    python main.py --output-dir ./my_data
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from config import DATASETS, HTTPConfig, StorageConfig
from logger_setup import setup_logging
from pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="nse-downloader",
        description=(
            "Download market data from NSE India and save as CSV files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                              # all datasets\n"
            "  python main.py --dataset top-gainers-losers  # single dataset\n"
            "  python main.py --dataset 52-week-high --sqlite\n"
            "  python main.py --output-dir ./data --list\n"
        ),
    )

    parser.add_argument(
        "--dataset",
        type=str,
        choices=list(DATASETS.keys()),
        nargs="+",
        default=None,
        help="One or more dataset keys to download. Omit to download all.",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save CSV files. Defaults to ./output.",
    )

    parser.add_argument(
        "--sqlite",
        action="store_true",
        default=False,
        help="Also persist data to a local SQLite database.",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Max retries per request (default: 3).",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="HTTP request timeout in seconds (default: 15).",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_datasets",
        help="List available dataset keys and exit.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging.",
    )

    parser.add_argument(
        "--ui",
        action="store_true",
        default=False,
        help="Launch the interactive web dashboard on http://127.0.0.1:8000.",
    )

    return parser


def list_datasets() -> None:
    """Print available dataset keys to stdout."""
    print("\nAvailable datasets:\n")
    for key, cfg in DATASETS.items():
        print(f"  {key:30s}  {cfg.name}")
        if cfg.description:
            print(f"  {'':30s}  {cfg.description}")
        print()


def main(argv: list[str] | None = None) -> int:
    """
    Application entry point.

    Returns
    -------
    int
        Exit code — 0 if all datasets succeeded, 1 otherwise.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    # ── Web UI mode ──────────────────────────────────────────────────
    if args.ui:
        from web_app import run_server
        run_server()
        return 0

    # ── List mode ────────────────────────────────────────────────────
    if args.list_datasets:
        list_datasets()
        return 0

    # ── Logging ──────────────────────────────────────────────────────
    import logging

    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=level)

    # ── Build configs from CLI args ──────────────────────────────────
    http_config = HTTPConfig()
    if args.retries is not None:
        http_config.max_retries = args.retries
    if args.timeout is not None:
        http_config.request_timeout = args.timeout

    storage_config = StorageConfig()
    if args.output_dir:
        storage_config.output_dir = args.output_dir

    # ── Run pipeline ─────────────────────────────────────────────────
    pipeline = Pipeline(
        http_config=http_config,
        storage_config=storage_config,
        use_sqlite=args.sqlite,
    )

    report = pipeline.run(dataset_keys=args.dataset)

    # ── Print summary ────────────────────────────────────────────────
    print(report.summary())

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
