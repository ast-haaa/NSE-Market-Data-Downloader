"""
Data validation layer for NSE Market Data Downloader.

Validates raw JSON payloads before they become DataFrames and
validates DataFrames before they are written to CSV.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from config import DatasetConfig
from logger_setup import get_logger

logger = get_logger("validator")


class ValidationError(Exception):
    """Raised when data fails a validation check."""


class DataValidator:
    """
    Stateless validator for NSE dataset payloads.

    Performs three layers of checks:
      1. **JSON-level** — is the payload a dict with the expected key?
      2. **Schema-level** — does the extracted list contain the expected columns?
      3. **Content-level** — are there duplicates or empty frames?
    """

    # ── public API ───────────────────────────────────────────────────

    @staticmethod
    def extract_records(
        raw_json: Dict[str, Any],
        dataset: DatasetConfig,
    ) -> List[Dict[str, Any]]:
        """
        Pull the list of records from the raw JSON, searching through
        known endpoint structures and fallback patterns.

        Returns the extracted list. Raises ``ValidationError`` if no
        usable data is found.
        """
        if not isinstance(raw_json, dict):
            raise ValidationError(
                f"Expected a JSON object but got {type(raw_json).__name__}"
            )

        # 1. Dataset-specific resolution
        if dataset.key == "top-gainers-losers":
            for sec in ("NIFTY", "allSec", "data"):
                val = raw_json.get(sec)
                if isinstance(val, dict) and isinstance(val.get("data"), list) and len(val["data"]) > 0:
                    logger.info(
                        "Extracted %d records from key '%s.data' for '%s'.",
                        len(val["data"]), sec, dataset.name,
                    )
                    return val["data"]
                if isinstance(val, list) and len(val) > 0:
                    logger.info(
                        "Extracted %d records from key '%s' for '%s'.",
                        len(val), sec, dataset.name,
                    )
                    return val

        elif dataset.key == "upper-band-hitters":
            upper = raw_json.get("upper")
            if isinstance(upper, dict):
                for sec in ("AllSec", "SecGtr20", "SecLwr20"):
                    sub = upper.get(sec)
                    if isinstance(sub, dict) and isinstance(sub.get("data"), list) and len(sub["data"]) > 0:
                        logger.info(
                            "Extracted %d records from key 'upper.%s.data' for '%s'.",
                            len(sub["data"]), sec, dataset.name,
                        )
                        return sub["data"]
                    if isinstance(sub, list) and len(sub) > 0:
                        logger.info(
                            "Extracted %d records from key 'upper.%s' for '%s'.",
                            len(sub), sec, dataset.name,
                        )
                        return sub
                if isinstance(upper.get("data"), list) and len(upper["data"]) > 0:
                    logger.info(
                        "Extracted %d records from key 'upper.data' for '%s'.",
                        len(upper["data"]), dataset.name,
                    )
                    return upper["data"]

        # 2. Candidate keys resolution (direct list or dict containing 'data')
        candidate_keys = [dataset.json_data_key]
        for fallback in ("data", "NIFTY", "allSec", "FOSec"):
            if fallback not in candidate_keys:
                candidate_keys.append(fallback)

        for key in candidate_keys:
            val = raw_json.get(key)
            if isinstance(val, list) and len(val) > 0:
                logger.info(
                    "Extracted %d records from key '%s' for '%s'.",
                    len(val), key, dataset.name,
                )
                return val
            if isinstance(val, dict) and isinstance(val.get("data"), list) and len(val["data"]) > 0:
                logger.info(
                    "Extracted %d records from key '%s.data' for '%s'.",
                    len(val["data"]), key, dataset.name,
                )
                return val["data"]

        # 3. Recursive fallback for any list of record dicts containing a symbol
        def _find_rows(obj: Any) -> Optional[List[Dict[str, Any]]]:
            if isinstance(obj, list) and len(obj) > 0:
                if isinstance(obj[0], dict) and any(k.lower() == "symbol" for k in obj[0].keys()):
                    return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    res = _find_rows(v)
                    if res is not None:
                        return res
            return None

        found = _find_rows(raw_json)
        if found:
            logger.info(
                "Extracted %d records via structural discovery for '%s'.",
                len(found), dataset.name,
            )
            return found

        # Nothing found — log available keys for debugging
        logger.error(
            "No usable data found for '%s'. Available keys: %s",
            dataset.name,
            list(raw_json.keys()),
        )
        raise ValidationError(
            f"No usable data list found for '{dataset.name}'. "
            f"Tried keys: {candidate_keys}. "
            f"Available keys: {list(raw_json.keys())}"
        )

    @staticmethod
    def validate_columns(
        df: pd.DataFrame,
        dataset: DatasetConfig,
    ) -> Tuple[bool, List[str]]:
        """
        Check whether the DataFrame contains the expected columns.

        Returns ``(passed, missing_columns)``.
        """
        actual = set(df.columns)
        missing = [col for col in dataset.expected_columns if col not in actual]
        if missing:
            logger.warning(
                "Column validation for '%s' — missing: %s. "
                "Available: %s",
                dataset.name, missing, sorted(actual),
            )
            return False, missing
        return True, []

    @staticmethod
    def remove_duplicates(
        df: pd.DataFrame,
        dataset: DatasetConfig,
    ) -> pd.DataFrame:
        """
        Drop exact duplicate rows and log if any were found.
        """
        before = len(df)
        df = df.drop_duplicates()
        after = len(df)
        removed = before - after
        if removed > 0:
            logger.info(
                "Removed %d duplicate row(s) from '%s'.",
                removed, dataset.name,
            )
        return df

    @classmethod
    def validate_dataframe(
        cls,
        df: pd.DataFrame,
        dataset: DatasetConfig,
        strict: bool = False,
    ) -> pd.DataFrame:
        """
        Run all content-level validations on the DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Data to validate.
        dataset : DatasetConfig
            Expected schema.
        strict : bool
            If True, raise on missing columns; otherwise log a warning.

        Returns
        -------
        pd.DataFrame
            The cleaned DataFrame.
        """
        if df.empty:
            raise ValidationError(
                f"DataFrame for '{dataset.name}' is empty after extraction."
            )

        # Normalize schema aliases for consistency across API versions
        if dataset.key == "52-week-high":
            if "highLowPrice" not in df.columns and "new52WHL" in df.columns:
                df["highLowPrice"] = df["new52WHL"]
        elif dataset.key == "upper-band-hitters":
            if "bandHitDate" not in df.columns and len(df) > 0:
                from datetime import datetime
                df["bandHitDate"] = datetime.now().strftime("%d-%b-%Y")

        passed, missing = cls.validate_columns(df, dataset)
        if not passed and strict:
            raise ValidationError(
                f"Missing required columns for '{dataset.name}': {missing}"
            )

        df = cls.remove_duplicates(df, dataset)

        logger.info(
            "Validation passed for '%s' — %d records, %d columns.",
            dataset.name, len(df), len(df.columns),
        )
        return df
