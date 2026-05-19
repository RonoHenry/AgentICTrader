"""
Test suite for Risk Engine FastAPI service.

TDD Phase: RED → GREEN → REFACTOR

Tests cover:
- Property: position_size * sl_distance_pips == 1% of equity (Hypothesis)
- Property: /validate always returns approved=False when daily_dd >= 3% (Hypothesis)
- /validate rejects on weekly_dd >= 6%, concurrent_trades >= 3, blackout, confidence < 0.65
- /validate approves when all checks pass
- GET /exposure returns correct shape {daily_dd_pct, weekly_dd_pct, open_trades, equity}
- GET /status returns correct shape {healthy, kill_switch_active}

**Validates: Requirements FR-7**
"""
from __future__ import annotations

import json
import sys
import os
import pytest
import fakeredis
from fastapi.testclient import TestClient
from hypothesis import given, settings as h_settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `services` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from services.risk_engine.main import (
    create_app,
    RiskEngine,
    ValidateRequest,
    ValidateResponse,
    ExposureResponse,
    StatusResponse,
    CONFIDENCE_FLOOR,
    MAX_DAILY_DD_PCT,
    MAX_WEEKLY_DD_PCT,
    MAX_CONCURRENT_TRADES,
    RISK_PER_TRADE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    """Provide a synchronous fakeredis client with decode_responses=True."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def client(fake_redis):
    """Provide a FastAPI TestClient backed by fakeredis."""
    app = create_app(redis_client=fake_redis)
    return TestClient(app)


@pytest.fixture
def client_with_clean_exposure(fake_redis):
    """Client with no exposure data in Redis (defaults apply)."""
    app = create_app(redis_client=fake_redis)
    return TestClient(app), fake_redis


# ---------------------------------------------------------------------------
# Helper: seed exposure state into fakeredis
# ---------------------------------------------------------------------------

def seed_exposure(redis_client, user_id: str, daily_dd_pct: float = 0.0,
                  weekly_dd_pct: float = 0.0, open_trades: int = 0,
                  equity: float = 10000.0):
    """Write a risk exposure snapshot directly into fakeredis."""
    key = f"risk:exposure:{user_id}"
    redis_client.set(key, json.dumps({
        "daily_dd_pct": daily_dd_pct,
        "weekly_dd_pct": weekly_dd_pct,
        "open_trades": open_trades,
        "equity": equity,
    }))


def seed_blackout(redis_client, instrument: str, active: bool = True,
                  event_name: str = "NFP", minutes_remaining: float = 10.0):
    """Write a blackout state directly into fakeredis."""
    key = f"blackout:{instrument}"
    redis_client.set(key, json.dumps({
        "active": active,
        "event_name": event_name,
        "minutes_remaining": minutes_remaining,
    }))


def seed_kill_switch(redis_client, active: bool = True):
    """Write the global kill switch state into fakeredis."""
    redis_client.set("risk:kill_switch:global", json.dumps({"active": active}))


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestPositionSizeProperty:
    """
    Property: position_size * sl_distance_pips == equity * 0.01 (exactly 1% risk).

    **Validates: Requirements FR-7**
    """

    @given(
        equity=st.floats(min_value=100.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
        sl_distance_pips=st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False),
    )
    @h_settings(max_examples=200)
    def test_position_size_always_risks_exactly_1_pct_of_equity(
        self, equity: float, sl_distance_pips: float
    ):
        """
        Property: for any valid equity and sl_distance_pips,
        position_size * sl_distance_pips == equity * RISK_PER_TRADE.

        **Validates: Requirements FR-7**
        """
        assume(sl_distance_pips > 0)
        assume(equity > 0)

        engine = RiskEngine(redis_client=None)
        position_size = engine.compute_position_size(equity, sl_distance_pips)

        risk_amount = position_size * sl_distance_pips
        expected_risk = equity * RISK_PER_TRADE

        assert abs(risk_amount - expected_risk) < 1e-9, (
            f"Expected risk {expected_risk}, got {risk_amount} "
            f"(equity={equity}, sl_pips={sl_distance_pips}, size={position_size})"
        )


class TestValidateDailyDDProperty:
    """
    Property: POST /validate always returns approved=False when daily_dd >= 3%.

    **Validates: Requirements FR-7**
    """

    @given(
        daily_dd=st.floats(min_value=3.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        confidence=st.floats(min_value=0.65, max_value=1.0, allow_nan=False, allow_infinity=False),
        sl_pips=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @h_settings(max_examples=200)
    def test_validate_always_rejects_when_daily_dd_at_or_above_limit(
        self, daily_dd: float, confidence: float, sl_pips: float
    ):
        """
        Property: /validate returns approved=False for any daily_dd >= MAX_DAILY_DD_PCT,
        regardless of other parameters.

        **Validates: Requirements FR-7**
        """
        assume(daily_dd >= MAX_DAILY_DD_PCT)
        assume(confidence >= CONFIDENCE_FLOOR)
        assume(sl_pips > 0)

        r = fakeredis.FakeRedis(decode_responses=True)
        seed_exposure(r, "user_prop", daily_dd_pct=daily_dd, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)

        app = create_app(redis_client=r)
        c = TestClient(app)

        response = c.post("/validate", json={
            "user_id": "user_prop",
            "instrument": "EURUSD",
            "confidence": confidence,
            "sl_distance_pips": sl_pips,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False, (
            f"Expected approved=False when daily_dd={daily_dd} >= {MAX_DAILY_DD_PCT}, "
            f"got approved={data['approved']}"
        )


# ---------------------------------------------------------------------------
# Unit Tests — /validate endpoint
# ---------------------------------------------------------------------------

class TestValidateEndpoint:
    """Unit tests for POST /validate."""

    def test_validate_rejects_when_weekly_dd_at_limit(self, client_with_clean_exposure):
        """Test: /validate rejects when weekly_dd >= 6%.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=6.0,
                      open_trades=0, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["reason"] is not None
        assert "weekly" in data["reason"].lower() or "drawdown" in data["reason"].lower()

    def test_validate_rejects_when_weekly_dd_above_limit(self, client_with_clean_exposure):
        """Test: /validate rejects when weekly_dd > 6%.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=7.5,
                      open_trades=0, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False

    def test_validate_rejects_when_concurrent_trades_at_limit(self, client_with_clean_exposure):
        """Test: /validate rejects when concurrent_trades >= 3.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=3, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["reason"] is not None
        assert "trade" in data["reason"].lower() or "concurrent" in data["reason"].lower()

    def test_validate_rejects_when_concurrent_trades_above_limit(self, client_with_clean_exposure):
        """Test: /validate rejects when concurrent_trades > 3.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=5, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False

    def test_validate_rejects_when_news_blackout_active(self, client_with_clean_exposure):
        """Test: /validate rejects when news blackout is active for the instrument.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)
        seed_blackout(redis_client, "EURUSD", active=True, event_name="NFP",
                      minutes_remaining=10.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["reason"] is not None
        assert "blackout" in data["reason"].lower() or "news" in data["reason"].lower()

    def test_validate_rejects_when_confidence_below_floor(self, client_with_clean_exposure):
        """Test: /validate rejects when confidence < 0.65.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.50,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["reason"] is not None
        assert "confidence" in data["reason"].lower()

    def test_validate_rejects_when_confidence_exactly_below_floor(self, client_with_clean_exposure):
        """Test: /validate rejects when confidence == 0.64 (just below floor).

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.64,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False

    def test_validate_approves_when_all_checks_pass(self, client_with_clean_exposure):
        """Test: /validate approves when all risk checks pass.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=1.0, weekly_dd_pct=2.0,
                      open_trades=1, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        assert data["reason"] is None
        assert data["position_size"] is not None
        assert data["position_size"] > 0

    def test_validate_approves_computes_correct_position_size(self, client_with_clean_exposure):
        """Test: /validate returns correct position_size = (equity * 0.01) / sl_pips.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        equity = 10000.0
        sl_pips = 20.0
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=equity)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": sl_pips,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        expected_size = (equity * 0.01) / sl_pips  # 5.0
        assert abs(data["position_size"] - expected_size) < 1e-9

    def test_validate_approves_with_equity_override(self, client_with_clean_exposure):
        """Test: /validate uses equity from request body when provided.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        # Seed exposure with equity=10000 but override with 20000 in request
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
            "equity": 20000.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True
        expected_size = (20000.0 * 0.01) / 10.0  # 20.0
        assert abs(data["position_size"] - expected_size) < 1e-9

    def test_validate_rejects_when_kill_switch_active(self, client_with_clean_exposure):
        """Test: /validate rejects when global kill switch is active.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)
        seed_kill_switch(redis_client, active=True)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
        assert data["reason"] is not None
        assert "kill" in data["reason"].lower() or "switch" in data["reason"].lower()

    def test_validate_approves_when_blackout_inactive(self, client_with_clean_exposure):
        """Test: /validate approves when blackout key exists but active=False.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=0.0, weekly_dd_pct=0.0,
                      open_trades=0, equity=10000.0)
        seed_blackout(redis_client, "EURUSD", active=False)

        response = client.post("/validate", json={
            "user_id": "user1",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True

    def test_validate_uses_default_exposure_when_not_in_redis(self, client):
        """Test: /validate uses default exposure (0.0, 0.0, 0, 10000.0) when key missing.

        **Validates: Requirements FR-7**
        """
        response = client.post("/validate", json={
            "user_id": "unknown_user",
            "instrument": "EURUSD",
            "confidence": 0.80,
            "sl_distance_pips": 10.0,
        })

        assert response.status_code == 200
        data = response.json()
        # With defaults all checks pass
        assert data["approved"] is True


# ---------------------------------------------------------------------------
# Unit Tests — GET /exposure endpoint
# ---------------------------------------------------------------------------

class TestExposureEndpoint:
    """Unit tests for GET /exposure."""

    def test_exposure_returns_correct_shape(self, client_with_clean_exposure):
        """Test: GET /exposure returns {daily_dd_pct, weekly_dd_pct, open_trades, equity}.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=1.5, weekly_dd_pct=3.0,
                      open_trades=2, equity=9500.0)

        response = client.get("/exposure?user_id=user1")

        assert response.status_code == 200
        data = response.json()

        assert "daily_dd_pct" in data
        assert "weekly_dd_pct" in data
        assert "open_trades" in data
        assert "equity" in data

    def test_exposure_returns_correct_values(self, client_with_clean_exposure):
        """Test: GET /exposure returns the exact values stored in Redis.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_exposure(redis_client, "user1", daily_dd_pct=1.5, weekly_dd_pct=3.0,
                      open_trades=2, equity=9500.0)

        response = client.get("/exposure?user_id=user1")

        assert response.status_code == 200
        data = response.json()

        assert abs(data["daily_dd_pct"] - 1.5) < 1e-9
        assert abs(data["weekly_dd_pct"] - 3.0) < 1e-9
        assert data["open_trades"] == 2
        assert abs(data["equity"] - 9500.0) < 1e-9

    def test_exposure_returns_defaults_when_key_missing(self, client):
        """Test: GET /exposure returns defaults (0.0, 0.0, 0, 10000.0) when key not in Redis.

        **Validates: Requirements FR-7**
        """
        response = client.get("/exposure?user_id=unknown_user")

        assert response.status_code == 200
        data = response.json()

        assert data["daily_dd_pct"] == 0.0
        assert data["weekly_dd_pct"] == 0.0
        assert data["open_trades"] == 0
        assert data["equity"] == 10000.0

    def test_exposure_requires_user_id(self, client):
        """Test: GET /exposure returns 422 when user_id is missing.

        **Validates: Requirements FR-7**
        """
        response = client.get("/exposure")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Unit Tests — GET /status endpoint
# ---------------------------------------------------------------------------

class TestStatusEndpoint:
    """Unit tests for GET /status."""

    def test_status_returns_correct_shape(self, client):
        """Test: GET /status returns {healthy, kill_switch_active}.

        **Validates: Requirements FR-7**
        """
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()

        assert "healthy" in data
        assert "kill_switch_active" in data

    def test_status_healthy_is_true(self, client):
        """Test: GET /status always returns healthy=True.

        **Validates: Requirements FR-7**
        """
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True

    def test_status_kill_switch_false_by_default(self, client):
        """Test: GET /status returns kill_switch_active=False when key not in Redis.

        **Validates: Requirements FR-7**
        """
        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is False

    def test_status_kill_switch_true_when_active(self, client_with_clean_exposure):
        """Test: GET /status returns kill_switch_active=True when global kill switch set.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_kill_switch(redis_client, active=True)

        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert data["kill_switch_active"] is True

    def test_status_kill_switch_false_when_explicitly_inactive(self, client_with_clean_exposure):
        """Test: GET /status returns kill_switch_active=False when kill switch set to inactive.

        **Validates: Requirements FR-7**
        """
        client, redis_client = client_with_clean_exposure
        seed_kill_switch(redis_client, active=False)

        response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch_active"] is False
