"""
Broker execution tools for OANDA v20 REST API.

Provides a thin async client around the OANDA v20 REST endpoints needed
by the execute_node to place, modify, and close positions.

Supported operations:
    - place_order  : Submit a market order with SL/TP
    - set_sl_tp    : Update stop-loss and take-profit on an open trade
    - close_position : Close an open trade at market
    - get_position_status : Fetch live trade state and unrealised P&L

Instrument normalisation:
    OANDA uses underscore-separated symbols (EUR_USD).
    All public functions accept normalised symbols (EURUSD) and convert
    automatically before sending requests.

Authentication:
    Every request carries an ``Authorization: Bearer <access_token>`` header.

Validates: Requirements FR-6 (Agentic Execution Loop), Task 37.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

__all__ = [
    "BrokerError",
    "OANDABrokerClient",
    "place_order",
    "set_sl_tp",
    "close_position",
    "get_position_status",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instrument normalisation map
# Normalised symbol (EURUSD) → OANDA symbol (EUR_USD)
# ---------------------------------------------------------------------------
_OANDA_SYMBOL_MAP: dict[str, str] = {
    "XAUUSD": "XAU_USD",
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "EURAUD": "EUR_AUD",
    "GBPAUD": "GBP_AUD",
    "USDJPY": "USD_JPY",
    "US100":  "NAS100_USD",
    "US30":   "US30_USD",
    "US500":  "SPX500_USD",
    "GER40":  "DE30_EUR",
    "BTCUSD": "BTC_USD",
    "ETHUSD": "ETH_USD",
}


def _to_oanda_instrument(symbol: str) -> str:
    """Convert a normalised symbol to OANDA format.

    Example:
        >>> _to_oanda_instrument("EURUSD")
        'EUR_USD'
        >>> _to_oanda_instrument("EUR_USD")  # already normalised — passthrough
        'EUR_USD'
    """
    return _OANDA_SYMBOL_MAP.get(symbol, symbol)


# ---------------------------------------------------------------------------
# BrokerError
# ---------------------------------------------------------------------------

class BrokerError(Exception):
    """Raised when the OANDA REST API returns an error or the request fails.

    Attributes:
        message:   Human-readable description.
        error_code: OANDA API error code string, if present.
    """

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


# ---------------------------------------------------------------------------
# OANDABrokerClient
# ---------------------------------------------------------------------------

class OANDABrokerClient:
    """Async HTTP client for the OANDA v20 REST API.

    Args:
        account_id:   OANDA account ID (e.g. ``"001-001-1234567-001"``).
        access_token: OANDA API access token.
        api_url:      Base URL for the OANDA REST API.
                      Defaults to the live endpoint.
                      Use ``"https://api-fxpractice.oanda.com"`` for practice.

    Example::

        client = OANDABrokerClient(
            account_id="001-001-1234567-001",
            access_token="my-token",
        )
        result = await place_order(client, order)
    """

    _DEFAULT_API_URL = "https://api-fxtrade.oanda.com"

    def __init__(
        self,
        account_id: str,
        access_token: str,
        api_url: str | None = None,
    ) -> None:
        self.account_id = account_id
        self.access_token = access_token
        self.api_url = api_url or self._DEFAULT_API_URL

    def _build_headers(self) -> dict[str, str]:
        """Return HTTP headers required by the OANDA v20 API."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept-Datetime-Format": "RFC3339",
        }

    def _accounts_url(self, path: str) -> str:
        """Build a full URL under /v3/accounts/{account_id}/…"""
        base = self.api_url.rstrip("/")
        return f"{base}/v3/accounts/{self.account_id}{path}"

    async def _make_request(
        self,
        endpoint: str,
        method: str = "POST",
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request to the OANDA REST API.

        Args:
            endpoint: Path relative to the account root
                      (e.g. ``"/orders"`` or ``"/trades/12345/close"``).
            method:   HTTP method: ``"GET"``, ``"POST"``, or ``"PUT"``.
            json:     Optional JSON body.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            BrokerError: On HTTP error, network failure, or malformed response.
        """
        url = self._accounts_url(endpoint)
        headers = self._build_headers()

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json,
                timeout=10.0,
            )

        try:
            data: dict[str, Any] = response.json()
        except Exception as exc:
            raise BrokerError(f"Failed to parse OANDA response: {exc}") from exc

        if not response.is_success:
            error_message = data.get("errorMessage", f"HTTP {response.status_code}")
            error_code = data.get("errorCode")
            raise BrokerError(error_message, error_code=error_code)

        return data


# ---------------------------------------------------------------------------
# Public broker tool functions
# ---------------------------------------------------------------------------

async def place_order(
    client: OANDABrokerClient,
    order: dict[str, Any],
) -> dict[str, Any]:
    """Place a market order via the OANDA v20 REST API.

    Args:
        client: Authenticated :class:`OANDABrokerClient`.
        order:  Order specification dict with keys:
                - ``instrument`` (str): Normalised symbol, e.g. ``"EURUSD"``.
                - ``direction`` (str): ``"LONG"`` or ``"SHORT"``.
                - ``size`` (float): Position size in lots / units.
                - ``stop_loss`` (float | None): Stop-loss price.
                - ``take_profit`` (float | None): Take-profit price.
                - ``setup_id`` (str | None): Agent setup reference.

    Returns:
        Dict with keys:
        - ``order_id`` (str): OANDA order transaction ID.
        - ``trade_id`` (str | None): OANDA trade ID (set when the order fills).

    Raises:
        BrokerError: On API failure, insufficient margin, or invalid request.
    """
    instrument = _to_oanda_instrument(order["instrument"])
    direction = order.get("direction", "LONG").upper()
    size = float(order.get("size", 0.01))

    # OANDA uses signed units: positive = buy (LONG), negative = sell (SHORT)
    units = size if direction == "LONG" else -size
    # Convert lots to units (1 lot = 100,000 units for forex)
    # For simplicity here we treat size directly as units; callers may adjust
    units_str = str(int(units * 100_000)) if abs(units) <= 10 else str(int(units))

    order_body: dict[str, Any] = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": units_str,
            "timeInForce": "FOK",  # Fill or Kill — standard for market orders
            "positionFill": "DEFAULT",
        }
    }

    # Attach SL/TP if provided
    sl_price = order.get("stop_loss")
    tp_price = order.get("take_profit")

    if sl_price is not None:
        order_body["order"]["stopLossOnFill"] = {
            "price": f"{sl_price:.5f}",
            "timeInForce": "GTC",
        }

    if tp_price is not None:
        order_body["order"]["takeProfitOnFill"] = {
            "price": f"{tp_price:.5f}",
            "timeInForce": "GTC",
        }

    try:
        response = await client._make_request("/orders", method="POST", json=order_body)
    except BrokerError:
        raise
    except Exception as exc:
        raise BrokerError(str(exc)) from exc

    # Check for OANDA-level error in a 200-OK response body
    if "errorMessage" in response:
        raise BrokerError(response["errorMessage"])

    order_create_txn = response.get("orderCreateTransaction", {})
    order_id: str = order_create_txn.get("id", "")

    order_fill_txn = response.get("orderFillTransaction", {})
    trade_opened = order_fill_txn.get("tradeOpened", {})
    trade_id: str | None = trade_opened.get("tradeID")

    logger.info(
        "place_order: order_id=%s trade_id=%s instrument=%s units=%s",
        order_id, trade_id, instrument, units_str,
    )

    return {"order_id": order_id, "trade_id": trade_id}


async def set_sl_tp(
    client: OANDABrokerClient,
    trade_id: str,
    sl_price: float,
    tp_price: float,
) -> bool:
    """Update the stop-loss and take-profit on an open trade.

    Args:
        client:   Authenticated :class:`OANDABrokerClient`.
        trade_id: OANDA trade ID to modify.
        sl_price: New stop-loss price.
        tp_price: New take-profit price.

    Returns:
        ``True`` on success.

    Raises:
        BrokerError: On API failure.
    """
    endpoint = f"/trades/{trade_id}/orders"
    payload: dict[str, Any] = {
        "stopLoss": {
            "price": f"{sl_price:.5f}",
            "timeInForce": "GTC",
        },
        "takeProfit": {
            "price": f"{tp_price:.5f}",
            "timeInForce": "GTC",
        },
    }

    try:
        await client._make_request(endpoint, method="PUT", json=payload)
    except BrokerError:
        raise
    except Exception as exc:
        raise BrokerError(str(exc)) from exc

    logger.info("set_sl_tp: trade_id=%s sl=%.5f tp=%.5f", trade_id, sl_price, tp_price)
    return True


async def close_position(
    client: OANDABrokerClient,
    trade_id: str,
) -> bool:
    """Close an open trade at market price.

    Args:
        client:   Authenticated :class:`OANDABrokerClient`.
        trade_id: OANDA trade ID to close.

    Returns:
        ``True`` on success.

    Raises:
        BrokerError: On API failure.
    """
    endpoint = f"/trades/{trade_id}/close"

    try:
        await client._make_request(endpoint, method="PUT")
    except BrokerError:
        raise
    except Exception as exc:
        raise BrokerError(str(exc)) from exc

    logger.info("close_position: trade_id=%s closed", trade_id)
    return True


async def get_position_status(
    client: OANDABrokerClient,
    trade_id: str,
) -> dict[str, Any]:
    """Fetch the current status of an open trade.

    Args:
        client:   Authenticated :class:`OANDABrokerClient`.
        trade_id: OANDA trade ID to query.

    Returns:
        Dict with keys:
        - ``status`` (str): Trade state, e.g. ``"OPEN"`` or ``"CLOSED"``.
        - ``unrealised_pnl`` (float): Current unrealised profit/loss in account currency.
        - ``current_price`` (float): Current market price for the trade.

    Raises:
        BrokerError: On API failure.
    """
    endpoint = f"/trades/{trade_id}"

    try:
        response = await client._make_request(endpoint, method="GET")
    except BrokerError:
        raise
    except Exception as exc:
        raise BrokerError(str(exc)) from exc

    trade = response.get("trade", {})

    status: str = trade.get("state", "UNKNOWN")
    unrealised_pnl: float = float(trade.get("unrealizedPL", 0.0))
    current_price: float = float(trade.get("price", 0.0))

    return {
        "status": status,
        "unrealised_pnl": unrealised_pnl,
        "current_price": current_price,
    }
