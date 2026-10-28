"""
Tests for the NSE HTTP client layer (nse_client.py).
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
import requests

from config import DATASETS, HTTPConfig
from nse_client import NSEClient, SessionInitError, APIRequestError


# ──────────────────────────────────────────────────────────────────────
# Session initialisation
# ──────────────────────────────────────────────────────────────────────


class TestSessionInit:
    """Tests for NSEClient.initialise_session."""

    @patch.object(NSEClient, "_create_session")
    def test_successful_session_init(self, mock_create):
        """Session init should GET the homepage and store cookies."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session.cookies.keys.return_value = ["nsit", "nseappid"]
        mock_create.return_value = mock_session

        client = NSEClient(HTTPConfig(max_retries=1, inter_request_delay=0))
        client.initialise_session()

        mock_session.get.assert_called_once()
        assert client._session is not None

    @patch.object(NSEClient, "_create_session")
    def test_session_init_failure_raises(self, mock_create):
        """Network failure during init should raise SessionInitError."""
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.ConnectionError("refused")
        mock_create.return_value = mock_session

        client = NSEClient(HTTPConfig(max_retries=1, inter_request_delay=0))
        with pytest.raises(SessionInitError, match="refused"):
            client.initialise_session()

    @patch.object(NSEClient, "_create_session")
    def test_session_init_timeout(self, mock_create):
        """Timeout during init should raise SessionInitError."""
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.Timeout("timed out")
        mock_create.return_value = mock_session

        client = NSEClient(HTTPConfig(max_retries=1, inter_request_delay=0))
        with pytest.raises(SessionInitError, match="timed out"):
            client.initialise_session()


# ──────────────────────────────────────────────────────────────────────
# Dataset fetching
# ──────────────────────────────────────────────────────────────────────


class TestFetchDataset:
    """Tests for NSEClient.fetch_dataset."""

    def _make_client_with_mock_session(self, mock_session):
        """Create an NSEClient and inject a pre-built mock session."""
        cfg = HTTPConfig(max_retries=2, inter_request_delay=0, retry_backoff_factor=0.01)
        client = NSEClient(cfg)
        client._session = mock_session
        return client

    def test_successful_fetch(self):
        """A 200 response with valid JSON should return the parsed dict."""
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"NIFTY": [{"symbol": "TCS"}]}
        mock_session.get.return_value = mock_resp

        client = self._make_client_with_mock_session(mock_session)
        ds = DATASETS["top-gainers-losers"]
        result = client.fetch_dataset(ds)

        assert "NIFTY" in result
        assert len(result["NIFTY"]) == 1

    def test_json_decode_error_retries(self):
        """Invalid JSON should trigger retries then raise APIRequestError."""
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = requests.exceptions.JSONDecodeError(
            "err", "doc", 0
        )
        mock_session.get.return_value = mock_resp

        client = self._make_client_with_mock_session(mock_session)
        ds = DATASETS["upper-band-hitters"]

        with pytest.raises(APIRequestError, match="Failed to fetch"):
            client.fetch_dataset(ds)

    def test_network_error_retries(self):
        """Connection errors should trigger retries then raise."""
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.ConnectionError("refused")

        client = self._make_client_with_mock_session(mock_session)
        ds = DATASETS["volume-gainers-spurts"]

        with pytest.raises(APIRequestError):
            client.fetch_dataset(ds)

    def test_403_triggers_session_refresh(self):
        """A 403 should re-initialise the session and retry."""
        mock_session = MagicMock()

        resp_403 = MagicMock()
        resp_403.status_code = 403

        resp_ok = MagicMock()
        resp_ok.status_code = 200
        resp_ok.raise_for_status = MagicMock()
        resp_ok.json.return_value = {"data": [{"symbol": "XYZ"}]}

        mock_session.get.side_effect = [resp_403, resp_ok]

        cfg = HTTPConfig(max_retries=2, inter_request_delay=0, retry_backoff_factor=0.01)
        client = NSEClient(cfg)
        client._session = mock_session

        # Patch initialise_session so it doesn't actually hit the network
        with patch.object(client, "initialise_session"):
            result = client.fetch_dataset(DATASETS["52-week-high"])

        assert "data" in result

    def test_http_500_retries(self):
        """Server errors should trigger retries."""
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_session.get.return_value = mock_resp

        client = self._make_client_with_mock_session(mock_session)
        ds = DATASETS["top-gainers-losers"]

        with pytest.raises(APIRequestError):
            client.fetch_dataset(ds)


# ──────────────────────────────────────────────────────────────────────
# Context manager
# ──────────────────────────────────────────────────────────────────────


class TestContextManager:
    """NSEClient should work as a context manager."""

    @patch.object(NSEClient, "_create_session")
    def test_enter_exit(self, mock_create):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_session.cookies.keys.return_value = []
        mock_create.return_value = mock_session

        with NSEClient(HTTPConfig(inter_request_delay=0)) as client:
            assert client._session is not None

        # After exit, close should have been called
        mock_session.close.assert_called_once()
