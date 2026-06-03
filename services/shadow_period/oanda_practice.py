"""
OANDAPracticeConfig — configuration for OANDA practice account connection.

Reads from environment variables:
  OANDA_PRACTICE_API_KEY      — practice account API key
  OANDA_PRACTICE_ACCOUNT_ID   — practice account ID
  OANDA_PRACTICE_BASE_URL     — defaults to https://api-fxpractice.oanda.com

Provides:
  - get_headers() -> dict  — Authorization headers for OANDA v20 REST API
  - get_streaming_url() -> str  — WebSocket streaming URL
  - is_configured() -> bool  — True if all required env vars are set
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

# Default URLs
_DEFAULT_BASE_URL = "https://api-fxpractice.oanda.com"
_DEFAULT_STREAMING_HOST = "stream-fxpractice.oanda.com"


class OANDAPracticeConfig:
    """Configuration for OANDA practice account connection.

    Reads credentials from environment variables. All required env vars
    must be set for ``is_configured()`` to return True.

    Required env vars:
        OANDA_PRACTICE_API_KEY      — practice account API key
        OANDA_PRACTICE_ACCOUNT_ID   — practice account ID

    Optional env vars:
        OANDA_PRACTICE_BASE_URL     — REST API base URL
                                      (default: https://api-fxpractice.oanda.com)
    """

    def __init__(self) -> None:
        self._api_key: str | None = os.environ.get("OANDA_PRACTICE_API_KEY")
        self._account_id: str | None = os.environ.get("OANDA_PRACTICE_ACCOUNT_ID")
        self._base_url: str = os.environ.get(
            "OANDA_PRACTICE_BASE_URL", _DEFAULT_BASE_URL
        )

    def is_configured(self) -> bool:
        """Return True if all required environment variables are set.

        Returns:
            True if OANDA_PRACTICE_API_KEY and OANDA_PRACTICE_ACCOUNT_ID
            are both set and non-empty.
        """
        return bool(self._api_key) and bool(self._account_id)

    def get_headers(self) -> dict:
        """Return Authorization headers for OANDA v20 REST API.

        Returns:
            Dict with Authorization and Content-Type headers.

        Raises:
            RuntimeError: If the API key is not configured.
        """
        if not self._api_key:
            raise RuntimeError(
                "OANDA_PRACTICE_API_KEY is not set. "
                "Cannot build authorization headers."
            )
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def get_streaming_url(self) -> str:
        """Return the WebSocket streaming URL for the practice account.

        Format:
            wss://stream-fxpractice.oanda.com/v3/accounts/{account_id}/pricing/stream

        Returns:
            Full streaming URL string.

        Raises:
            RuntimeError: If the account ID is not configured.
        """
        if not self._account_id:
            raise RuntimeError(
                "OANDA_PRACTICE_ACCOUNT_ID is not set. "
                "Cannot build streaming URL."
            )
        return (
            f"wss://{_DEFAULT_STREAMING_HOST}"
            f"/v3/accounts/{self._account_id}/pricing/stream"
        )

    @property
    def base_url(self) -> str:
        """Return the REST API base URL."""
        return self._base_url

    @property
    def account_id(self) -> str | None:
        """Return the practice account ID."""
        return self._account_id
