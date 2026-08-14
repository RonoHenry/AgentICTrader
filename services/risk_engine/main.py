"""Risk Engine FastAPI service.

Validates trade setups against risk rules and maintains exposure state in Redis.

Risk rules (all must pass for approved=True):
  1. confidence >= CONFIDENCE_FLOOR (0.65)          — hard confidence floor
  2. kill_switch_active == False                     — global kill switch
  3. daily_dd_pct < MAX_DAILY_DD_PCT (3.0%)         — daily drawdown limit
  4. weekly_dd_pct < MAX_WEEKLY_DD_PCT (6.0%)       — weekly drawdown limit
  5. open_trades < MAX_CONCURRENT_TRADES (3)         — max concurrent trades
  6. blackout:{instrument} → active == False         — no news blackout

Position size formula:
  position_size = (equity * RISK_PER_TRADE) / sl_distance_pips
  → guarantees position_size * sl_distance_pips == equity * 0.01 (exactly 1% risk)

Redis key patterns used:
  risk:exposure:{user_id}   → {daily_dd_pct, weekly_dd_pct, open_trades, equity}
  blackout:{instrument}     → {active, event_name, minutes_remaining}
  risk:kill_switch:global   → {active}
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_FLOOR: float = 0.65
MAX_DAILY_DD_PCT: float = 3.0
MAX_WEEKLY_DD_PCT: float = 6.0
MAX_CONCURRENT_TRADES: int = 3
RISK_PER_TRADE: float = 0.01  # 1%

# Redis key patterns
_EXPOSURE_KEY = "risk:exposure:{user_id}"
_BLACKOUT_KEY = "blackout:{instrument}"
_KILL_SWITCH_KEY = "risk:kill_switch:global"

# Default exposure values when Redis key is absent
_DEFAULT_EXPOSURE = {
    "daily_dd_pct": 0.0,
    "weekly_dd_pct": 0.0,
    "open_trades": 0,
    "equity": 10000.0,
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    """Request body for POST /validate."""

    user_id: str
    instrument: str
    confidence: float          # 0.0–1.0
    sl_distance_pips: float    # stop-loss distance in pips
    equity: Optional[float] = None  # override equity; if None, read from Redis


class ValidateResponse(BaseModel):
    """Response body for POST /validate."""

    approved: bool
    reason: Optional[str] = None          # rejection reason when approved=False
    position_size: Optional[float] = None  # computed when approved=True


class ExposureResponse(BaseModel):
    """Response body for GET /exposure."""

    daily_dd_pct: float
    weekly_dd_pct: float
    open_trades: int
    equity: float


class StatusResponse(BaseModel):
    """Response body for GET /status."""

    healthy: bool
    kill_switch_active: bool


# ---------------------------------------------------------------------------
# RiskEngine — core validation logic
# ---------------------------------------------------------------------------

class RiskEngine:
    """Core risk validation logic backed by a synchronous Redis client.

    The redis_client is expected to be a synchronous client (e.g. fakeredis.FakeRedis
    or redis.Redis) with ``decode_responses=True``.  In tests we inject fakeredis;
    in production a real redis.Redis client is used.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, request: ValidateRequest) -> ValidateResponse:
        """Validate a trade setup against all risk rules.

        Returns a ValidateResponse with approved=True and a computed
        position_size when all checks pass, or approved=False with a
        human-readable reason when any check fails.
        """
        # 1. Confidence floor
        if request.confidence < CONFIDENCE_FLOOR:
            return ValidateResponse(
                approved=False,
                reason=f"confidence {request.confidence:.2f} is below floor {CONFIDENCE_FLOOR}",
            )

        # 2. Kill switch
        if self._is_kill_switch_active():
            return ValidateResponse(
                approved=False,
                reason="kill switch is active — trading halted",
            )

        # 3. Load exposure state
        exposure = self._get_exposure(request.user_id)

        # 4. Daily drawdown limit
        if exposure["daily_dd_pct"] >= MAX_DAILY_DD_PCT:
            return ValidateResponse(
                approved=False,
                reason=(
                    f"daily drawdown {exposure['daily_dd_pct']:.2f}% "
                    f"has reached the {MAX_DAILY_DD_PCT}% limit"
                ),
            )

        # 5. Weekly drawdown limit
        if exposure["weekly_dd_pct"] >= MAX_WEEKLY_DD_PCT:
            return ValidateResponse(
                approved=False,
                reason=(
                    f"weekly drawdown {exposure['weekly_dd_pct']:.2f}% "
                    f"has reached the {MAX_WEEKLY_DD_PCT}% limit"
                ),
            )

        # 6. Concurrent trades limit
        if exposure["open_trades"] >= MAX_CONCURRENT_TRADES:
            return ValidateResponse(
                approved=False,
                reason=(
                    f"concurrent trades {exposure['open_trades']} "
                    f"has reached the {MAX_CONCURRENT_TRADES} trade limit"
                ),
            )

        # 7. News blackout
        if self._is_blackout_active(request.instrument):
            return ValidateResponse(
                approved=False,
                reason=f"news blackout is active for {request.instrument}",
            )

        # All checks passed — compute position size
        equity = request.equity if request.equity is not None else exposure["equity"]
        position_size = self.compute_position_size(equity, request.sl_distance_pips)

        return ValidateResponse(
            approved=True,
            position_size=position_size,
        )

    def get_exposure(self, user_id: str) -> ExposureResponse:
        """Return the current risk exposure for *user_id*.

        Reads from Redis key ``risk:exposure:{user_id}``.  Returns defaults
        when the key is absent.
        """
        data = self._get_exposure(user_id)
        return ExposureResponse(
            daily_dd_pct=data["daily_dd_pct"],
            weekly_dd_pct=data["weekly_dd_pct"],
            open_trades=int(data["open_trades"]),
            equity=data["equity"],
        )

    def get_status(self) -> StatusResponse:
        """Return service health and global kill switch state."""
        return StatusResponse(
            healthy=True,
            kill_switch_active=self._is_kill_switch_active(),
        )

    def compute_position_size(self, equity: float, sl_distance_pips: float) -> float:
        """Compute position size so that risk == equity * RISK_PER_TRADE.

        Formula:
            position_size = (equity * RISK_PER_TRADE) / sl_distance_pips

        This guarantees:
            position_size * sl_distance_pips == equity * RISK_PER_TRADE  (1% risk)
        """
        return (equity * RISK_PER_TRADE) / sl_distance_pips

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_exposure(self, user_id: str) -> dict:
        """Read exposure from Redis; return defaults if key is absent."""
        if self._redis is None:
            return dict(_DEFAULT_EXPOSURE)
        key = _EXPOSURE_KEY.format(user_id=user_id)
        raw = self._redis.get(key)
        if raw is None:
            return dict(_DEFAULT_EXPOSURE)
        return json.loads(raw)

    def _is_blackout_active(self, instrument: str) -> bool:
        """Return True if a news blackout is active for *instrument*."""
        if self._redis is None:
            return False
        key = _BLACKOUT_KEY.format(instrument=instrument)
        raw = self._redis.get(key)
        if raw is None:
            return False
        data = json.loads(raw)
        return bool(data.get("active", False))

    def _is_kill_switch_active(self) -> bool:
        """Return True if the global kill switch is active."""
        if self._redis is None:
            return False
        raw = self._redis.get(_KILL_SWITCH_KEY)
        if raw is None:
            return False
        data = json.loads(raw)
        return bool(data.get("active", False))


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(redis_client=None) -> FastAPI:
    """Create and return the FastAPI application.

    Args:
        redis_client: A synchronous Redis-compatible client.  Pass a
            ``fakeredis.FakeRedis`` instance in tests; leave as ``None``
            (or pass a real ``redis.Redis``) in production.

    Returns:
        Configured FastAPI application with /validate, /exposure, /status routes.
    """
    app = FastAPI(title="Risk Engine", version="1.0.0")
    engine = RiskEngine(redis_client=redis_client)

    @app.post("/validate", response_model=ValidateResponse)
    def validate_trade(request: ValidateRequest) -> ValidateResponse:
        """Validate a trade setup against all risk rules."""
        return engine.validate(request)

    @app.get("/exposure", response_model=ExposureResponse)
    def get_exposure(user_id: str = Query(..., description="User ID")) -> ExposureResponse:
        """Return current risk exposure for a user."""
        return engine.get_exposure(user_id)

    @app.get("/status", response_model=StatusResponse)
    def get_status() -> StatusResponse:
        """Return service health and kill switch state."""
        return engine.get_status()

    return app


# ---------------------------------------------------------------------------
# Entry point — module-level app for `uvicorn services.risk_engine.main:app`
# ---------------------------------------------------------------------------

def _build_redis_client():
    """Build the production Redis client from REDIS_HOST/REDIS_PORT env vars."""
    import redis

    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )


app = create_app(redis_client=_build_redis_client())

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.risk_engine.main:app",
        host="0.0.0.0",
        port=int(os.getenv("RISK_ENGINE_PORT", "8004")),
    )
