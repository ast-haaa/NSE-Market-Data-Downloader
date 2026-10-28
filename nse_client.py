"""
NSE HTTP Client — session-aware data acquisition layer.

Handles:
  • Cookie priming via the NSE homepage (using browser TLS impersonation)
  • Automatic retries with exponential backoff
  • Rate-limiting between successive requests
  • Transparent JSON parsing and error surfacing

Uses ``curl_cffi`` to impersonate a real browser's TLS fingerprint,
which is required to pass NSE's Akamai WAF.  Falls back to ``requests``
if ``curl_cffi`` is unavailable.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from config import (
    NSE_BASE_URL,
    NSE_HOME_URL,
    DEFAULT_HEADERS,
    DatasetConfig,
    HTTPConfig,
)
from logger_setup import get_logger

logger = get_logger("nse_client")

# ── Try to use curl_cffi for TLS impersonation; fall back to requests ──
try:
    from curl_cffi.requests import Session as CurlSession
    _USE_CURL_CFFI = True
    logger.debug("Using curl_cffi for browser TLS impersonation.")
except ImportError:
    CurlSession = None  # type: ignore[assignment, misc]
    _USE_CURL_CFFI = False
    logger.debug("curl_cffi not available — falling back to requests.")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class NSEClientError(Exception):
    """Base exception for NSE client failures."""


class SessionInitError(NSEClientError):
    """Raised when cookie-priming on the NSE homepage fails."""


class APIRequestError(NSEClientError):
    """Raised when an API request fails after all retries."""


class NSEClient:
    """
    HTTP client that manages a session tailored for NSE India.

    When ``curl_cffi`` is installed the client impersonates a real
    Chrome browser at the TLS level, which is necessary to pass NSE's
    Akamai / Cloudflare WAF.  Otherwise it falls back to plain
    ``requests`` (which may receive 403s).

    Usage::

        client = NSEClient()
        data = client.fetch_dataset(dataset_config)
    """

    # Browser to impersonate (curl_cffi identifier)
    _IMPERSONATE = "chrome124"

    def __init__(self, http_config: Optional[HTTPConfig] = None) -> None:
        self._cfg = http_config or HTTPConfig()
        self._session: Any = None          # CurlSession or requests.Session
        self._last_request_ts: float = 0.0

    # ── public API ───────────────────────────────────────────────────

    def _create_session(self) -> Any:
        """Create an underlying HTTP session, preferring curl_cffi when available."""
        if _USE_CURL_CFFI:
            return CurlSession(impersonate=self._IMPERSONATE)

        session = requests.Session()
        retry_strategy = Retry(
            total=self._cfg.max_retries,
            backoff_factor=self._cfg.retry_backoff_factor,
            status_forcelist=list(self._cfg.retry_status_codes),
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def initialise_session(self) -> None:
        """
        Create a fresh session and prime it by visiting the NSE
        homepage so that the necessary cookies (``nsit``,
        ``nseappid``, ``ak_bmsc`` …) are set.
        """
        self._session = self._create_session()
        self._session.headers.update(DEFAULT_HEADERS)

        # Cookie priming
        logger.info("Initialising NSE session (cookie priming) …")
        try:
            resp = self._session.get(
                NSE_HOME_URL, timeout=self._cfg.session_init_timeout
            )
            status = getattr(resp, "status_code", 200)
            if isinstance(status, int) and status >= 400:
                raise requests.HTTPError(
                    f"{status} during session init",
                    response=resp,
                )
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()

            cookies = (
                list(self._session.cookies.keys())
                if hasattr(self._session, "cookies") and hasattr(self._session.cookies, "keys")
                else []
            )
            logger.info(
                "Session initialised — status %s, cookies: %s",
                status,
                cookies,
            )
        except Exception as exc:
            logger.error("Session initialisation failed: %s", exc)
            raise SessionInitError(
                f"Could not prime NSE session: {exc}"
            ) from exc

    def fetch_dataset(self, dataset: DatasetConfig) -> Dict[str, Any]:
        """
        Fetch raw JSON for the given *dataset*.

        Returns the parsed JSON dict.  Raises ``APIRequestError`` on
        unrecoverable failure.
        """
        if self._session is None:
            self.initialise_session()

        url = NSE_BASE_URL + dataset.api_path
        referer = NSE_BASE_URL + dataset.page_path

        self._rate_limit()

        logger.info(
            "Fetching dataset '%s' from %s", dataset.name, url,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._session.get(
                    url,
                    headers={"Referer": referer},
                    timeout=self._cfg.request_timeout,
                )
                self._last_request_ts = time.monotonic()

                if resp.status_code in (401, 403):
                    # Session may have expired — re-prime and retry
                    logger.warning(
                        "HTTP %d on attempt %d — re-initialising session.",
                        resp.status_code,
                        attempt,
                    )
                    self.initialise_session()
                    continue

                if resp.status_code >= 400:
                    raise requests.HTTPError(
                        f"HTTP {resp.status_code}",
                        response=resp,
                    )

                data = resp.json()
                logger.info(
                    "Dataset '%s' fetched — HTTP %d, payload keys: %s",
                    dataset.name,
                    resp.status_code,
                    list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                )
                return data

            except (ValueError, KeyError) as exc:
                # JSON decode errors
                logger.error(
                    "Invalid JSON on attempt %d for '%s': %s",
                    attempt, dataset.name, exc,
                )
                last_error = exc
            except Exception as exc:
                logger.error(
                    "Request error on attempt %d for '%s': %s",
                    attempt, dataset.name, exc,
                )
                last_error = exc

            # exponential backoff
            backoff = self._cfg.retry_backoff_factor * (2 ** (attempt - 1))
            logger.info("Backing off %.1fs before retry …", backoff)
            time.sleep(backoff)

        raise APIRequestError(
            f"Failed to fetch '{dataset.name}' after "
            f"{self._cfg.max_retries} attempts: {last_error}"
        )

    def close(self) -> None:
        """Close the underlying session."""
        if self._session:
            self._session.close()
            self._session = None
            logger.info("NSE session closed.")

    # ── context-manager support ──────────────────────────────────────

    def __enter__(self) -> "NSEClient":
        self.initialise_session()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ── private helpers ──────────────────────────────────────────────

    def _rate_limit(self) -> None:
        """Enforce a minimum delay between consecutive requests."""
        if self._last_request_ts:
            elapsed = time.monotonic() - self._last_request_ts
            if elapsed < self._cfg.inter_request_delay:
                wait = self._cfg.inter_request_delay - elapsed
                logger.debug("Rate-limiting: sleeping %.2fs", wait)
                time.sleep(wait)
