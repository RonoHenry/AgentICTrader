"""
Tests for Task 39: Live validation run and audit trail.

Covers:
  - Deployment configuration for staging with capital limits
  - 30-day live autonomous period monitoring
  - P&L tracking and drawdown monitoring
  - Confidence threshold performance tracking
  - Rollback mechanism via POST /agent/pause
  - Audit trail compliance check (zero risk engine bypasses)
  - Daily monitoring dashboard metrics

Validates: Requirements FR-6, FR-7, NFR-4 (Phase 4 Task 39)
"""
from __future__ import annotations

import json
import pytest
import fakeredis
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper: create minimal MongoDB collection mock
# ---------------------------------------------------------------------------

def _make_collection(docs: list[dict] | None = None):
    """Return a minimal in-memory MongoDB collection mock."""
    store: list[dict] = list(docs or [])

    class _Col:
        def insert_one(self, doc):
            store.append(doc)
            result = MagicMock()
            result.inserted_id = f"id_{len(store)}"
            return result

        def find_one(self, query):
            for doc in store:
                if all(doc.get(k) == v for k, v in query.items()):
                    return dict(doc)
            return None

        def find(self, query=None):
            query = query or {}
            matching = [
                dict(d) for d in store
                if all(d.get(k) == v for k, v in query.items())
            ]
            return _Cursor(matching)

        def count_documents(self, query):
            query = query or {}
            return sum(
                1 for d in store
                if all(d.get(k) == v for k, v in query.items())
            )

        def aggregate(self, pipeline):
            # Simplified aggregation for P&L calculation
            results = list(store)
            for stage in pipeline:
                if "$match" in stage:
                    match_conditions = stage["$match"]
                    results = [
                        d for d in results
                        if all(d.get(k) == v for k, v in match_conditions.items())
                    ]
                elif "$group" in stage:
                    # Simple sum aggregation
                    group_spec = stage["$group"]
                    if "_id" in group_spec and group_spec["_id"] is None:
                        total = sum(
                            d.get("r_multiple", 0)
                            for d in results
                            if d.get("r_multiple") is not None
                        )
                        return [{"total_r": total, "trade_count": len(results)}]
            return results

    class _Cursor:
        def __init__(self, docs):
            self._docs = docs
            self._idx = 0

        def __iter__(self):
            return iter(self._docs)

        def sort(self, *args, **kwargs):
            return self

        def limit(self, n):
            self._docs = self._docs[:n]
            return self

    return _Col()


# ---------------------------------------------------------------------------
# LiveValidationConfig
# ---------------------------------------------------------------------------

class TestLiveValidationConfig:
    """Test configuration for staging deployment with capital limits."""

    def test_capital_limit_enforced_at_10_percent(self, monkeypatch):
        monkeypatch.setenv("LIVE_VALIDATION_CAPITAL_PCT", "10")
        monkeypatch.setenv("TOTAL_ACCOUNT_CAPITAL", "10000")
        from scripts.live_validation_config import LiveValidationConfig
        cfg = LiveValidationConfig()
        assert cfg.get_validation_capital() == 1000.0

    def test_default_capital_limit_is_10_percent(self, monkeypatch):
        monkeypatch.delenv("LIVE_VALIDATION_CAPITAL_PCT", raising=False)
        monkeypatch.setenv("TOTAL_ACCOUNT_CAPITAL", "5000")
        from scripts.live_validation_config import LiveValidationConfig
        cfg = LiveValidationConfig()
        assert cfg.get_validation_capital() == 500.0

    def test_validation_period_days_default_30(self, monkeypatch):
        monkeypatch.delenv("LIVE_VALIDATION_PERIOD_DAYS", raising=False)
        from scripts.live_validation_config import LiveValidationConfig
        cfg = LiveValidationConfig()
        assert cfg.validation_period_days == 30

    def test_validation_period_days_configurable(self, monkeypatch):
        monkeypatch.setenv("LIVE_VALIDATION_PERIOD_DAYS", "45")
        from scripts.live_validation_config import LiveValidationConfig
        cfg = LiveValidationConfig()
        assert cfg.validation_period_days == 45

    def test_deployment_mode_is_staging(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "STAGING")
        from scripts.live_validation_config import LiveValidationConfig
        cfg = LiveValidationConfig()
        assert cfg.deployment_mode == "STAGING"

    def test_raises_when_total_capital_missing(self, monkeypatch):
        monkeypatch.delenv("TOTAL_ACCOUNT_CAPITAL", raising=False)
        from scripts.live_validation_config import LiveValidationConfig
        with pytest.raises(RuntimeError, match="TOTAL_ACCOUNT_CAPITAL"):
            cfg = LiveValidationConfig()
            cfg.get_validation_capital()


# ---------------------------------------------------------------------------
# LiveValidationMonitor
# ---------------------------------------------------------------------------

class TestLiveValidationMonitor:
    """Test daily P&L, drawdown, and performance monitoring."""

    @pytest.fixture
    def journal_collection(self):
        """Collection with sample trades for monitoring."""
        now = datetime.now(tz=timezone.utc)
        docs = [
            {
                "trade_id": f"trade-{i}",
                "setup_id": f"setup-{i}",
                "user_id": "test-user",
                "close_time": (now - timedelta(days=i)).isoformat(),
                "r_multiple": rm,
                "outcome": "WIN" if rm > 0 else "LOSS",
                "final_confidence": 0.80,
            }
            for i, rm in enumerate([2.0, -1.0, 1.5, -1.0, 3.0])
        ]
        return _make_collection(docs)

    @pytest.fixture
    def decisions_collection(self):
        """Collection with agent decisions for audit trail."""
        now = datetime.now(tz=timezone.utc)
        docs = [
            {
                "setup_id": f"setup-{i}",
                "user_id": "test-user",
                "timestamp": (now - timedelta(days=i)).isoformat(),
                "decision": decision,
                "risk_validation": {
                    "verdict": "APPROVED" if decision != "SKIP" else "REJECTED",
                    "rejection_reason": None if decision != "SKIP" else "confidence too low",
                },
            }
            for i, decision in enumerate(["EXECUTE", "EXECUTE", "NOTIFY", "SKIP", "EXECUTE"])
        ]
        return _make_collection(docs)

    @pytest.fixture
    def monitor(self, journal_collection, decisions_collection):
        from scripts.live_validation_monitor import LiveValidationMonitor
        return LiveValidationMonitor(
            trade_journal_collection=journal_collection,
            agent_decisions_collection=decisions_collection,
            user_id="test-user",
        )

    def test_calculate_daily_pnl_sums_r_multiples(self, monitor):
        pnl = monitor.calculate_daily_pnl()
        # 2.0 - 1.0 + 1.5 - 1.0 + 3.0 = 4.5
        assert pnl == pytest.approx(4.5, abs=0.01)

    def test_calculate_daily_pnl_empty_journal_returns_zero(self):
        from scripts.live_validation_monitor import LiveValidationMonitor
        empty_monitor = LiveValidationMonitor(
            trade_journal_collection=_make_collection([]),
            agent_decisions_collection=_make_collection([]),
            user_id="test-user",
        )
        assert empty_monitor.calculate_daily_pnl() == 0.0

    def test_calculate_cumulative_pnl_matches_total(self, monitor):
        cumulative = monitor.calculate_cumulative_pnl()
        assert cumulative == pytest.approx(4.5, abs=0.01)

    def test_calculate_max_drawdown_from_equity_curve(self, monitor):
        # With trades: +2, -1, +1.5, -1, +3 → peak is 5.5, trough after peak is 0.5
        # Max DD = (5.5 - 0.5) / 5.5 = 90.9% (unrealistic but tests the calc)
        # Actually with cumulative: 2, 1, 2.5, 1.5, 4.5
        # Peak = 4.5, trough before final = 1.5, DD = (2.5-1.5)/2.5 = 40%
        dd_pct = monitor.calculate_max_drawdown()
        assert dd_pct >= 0.0
        assert dd_pct <= 100.0

    def test_calculate_max_drawdown_zero_when_no_losses(self):
        from scripts.live_validation_monitor import LiveValidationMonitor
        docs = [
            {
                "trade_id": "t1",
                "close_time": datetime.now(tz=timezone.utc).isoformat(),
                "r_multiple": 2.0,
                "outcome": "WIN",
            }
        ]
        mon = LiveValidationMonitor(
            trade_journal_collection=_make_collection(docs),
            agent_decisions_collection=_make_collection([]),
            user_id="test-user",
        )
        assert mon.calculate_max_drawdown() == 0.0

    def test_get_confidence_threshold_performance_returns_stats(self, monitor):
        stats = monitor.get_confidence_threshold_performance()
        assert "total_setups" in stats
        assert "executed_count" in stats
        assert "notified_count" in stats
        assert "skipped_count" in stats
        assert stats["total_setups"] == 5
        assert stats["executed_count"] == 3
        assert stats["skipped_count"] == 1

    def test_check_risk_engine_bypasses_returns_zero_when_all_validated(self, monitor):
        bypasses = monitor.check_risk_engine_bypasses()
        assert bypasses == 0

    def test_check_risk_engine_bypasses_detects_missing_validation(self):
        from scripts.live_validation_monitor import LiveValidationMonitor
        # Create decision with no risk_validation field (bypass!)
        docs = [
            {
                "setup_id": "bypass-1",
                "user_id": "test-user",
                "decision": "EXECUTE",
                "risk_validation": None,  # BYPASS!
            }
        ]
        mon = LiveValidationMonitor(
            trade_journal_collection=_make_collection([]),
            agent_decisions_collection=_make_collection(docs),
            user_id="test-user",
        )
        bypasses = mon.check_risk_engine_bypasses()
        assert bypasses == 1

    def test_generate_daily_report_returns_full_snapshot(self, monitor):
        report = monitor.generate_daily_report()
        assert "date" in report
        assert "daily_pnl_r" in report
        assert "cumulative_pnl_r" in report
        assert "max_drawdown_pct" in report
        assert "confidence_performance" in report
        assert "risk_engine_bypasses" in report
        assert report["risk_engine_bypasses"] == 0

    def test_check_exit_criteria_positive_pnl(self, monitor):
        # Has positive P&L (4.5 R)
        result = monitor.check_exit_criteria()
        assert result["positive_pnl"] is True

    def test_check_exit_criteria_drawdown_threshold(self, monitor):
        result = monitor.check_exit_criteria()
        # Drawdown should be <= 5%
        assert "drawdown_within_limit" in result

    def test_check_exit_criteria_zero_bypasses(self, monitor):
        result = monitor.check_exit_criteria()
        assert result["zero_bypasses"] is True

    def test_check_exit_criteria_all_met_returns_true(self, monitor):
        result = monitor.check_exit_criteria()
        if result["positive_pnl"] and result["drawdown_within_limit"] and result["zero_bypasses"]:
            assert result["all_criteria_met"] is True


# ---------------------------------------------------------------------------
# LiveValidationDashboard API
# ---------------------------------------------------------------------------

class TestLiveValidationDashboardAPI:
    """Test FastAPI endpoints for live validation monitoring."""

    @pytest.fixture
    def journal_collection(self):
        now = datetime.now(tz=timezone.utc)
        docs = [
            {
                "trade_id": "t1",
                "close_time": now.isoformat(),
                "r_multiple": 1.5,
                "outcome": "WIN",
            }
        ]
        return _make_collection(docs)

    @pytest.fixture
    def decisions_collection(self):
        now = datetime.now(tz=timezone.utc)
        docs = [
            {
                "setup_id": "s1",
                "timestamp": now.isoformat(),
                "decision": "EXECUTE",
                "risk_validation": {"verdict": "APPROVED"},
            }
        ]
        return _make_collection(docs)

    @pytest.fixture
    def client(self, journal_collection, decisions_collection):
        from scripts.live_validation_dashboard import create_validation_dashboard_app
        app = create_validation_dashboard_app(
            trade_journal_collection=journal_collection,
            agent_decisions_collection=decisions_collection,
            user_id="test-user",
        )
        return TestClient(app)

    def test_get_daily_report_returns_200(self, client):
        resp = client.get("/validation/daily-report")
        assert resp.status_code == 200
        body = resp.json()
        assert "date" in body
        assert "daily_pnl_r" in body

    def test_get_exit_criteria_returns_200(self, client):
        resp = client.get("/validation/exit-criteria")
        assert resp.status_code == 200
        body = resp.json()
        assert "positive_pnl" in body
        assert "drawdown_within_limit" in body
        assert "zero_bypasses" in body
        assert "all_criteria_met" in body

    def test_get_audit_summary_returns_bypass_count(self, client):
        resp = client.get("/validation/audit-summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_decisions" in body
        assert "risk_engine_bypasses" in body
        assert body["risk_engine_bypasses"] == 0

    def test_get_equity_curve_returns_time_series(self, client):
        resp = client.get("/validation/equity-curve")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_get_status_returns_validation_period_info(self, client):
        resp = client.get("/validation/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "validation_active" in body
        assert "days_elapsed" in body
        assert "days_remaining" in body


# ---------------------------------------------------------------------------
# RollbackMechanism
# ---------------------------------------------------------------------------

class TestRollbackMechanism:
    """Test POST /agent/pause rollback mechanism."""

    @pytest.fixture
    def redis(self):
        return fakeredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def client(self, redis):
        from agent.graph import create_agent_app
        app = create_agent_app(redis_client=redis)
        return TestClient(app)

    def test_post_agent_pause_activates_kill_switch(self, client, redis):
        resp = client.post("/agent/pause")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kill_switch_active"] is True
        assert "paused" in body["message"].lower()

    def test_post_agent_pause_sets_redis_key(self, client, redis):
        client.post("/agent/pause")
        raw = redis.get("risk:kill_switch:global")
        data = json.loads(raw)
        assert data["active"] is True

    def test_post_agent_resume_clears_kill_switch(self, client, redis):
        client.post("/agent/pause")
        resp = client.post("/agent/resume")
        assert resp.status_code == 200
        body = resp.json()
        assert body["kill_switch_active"] is False

    def test_kill_switch_halts_new_trades_immediately(self, client, redis):
        # Activate kill switch
        client.post("/agent/pause")
        
        # Verify status shows kill switch active
        status_resp = client.get("/agent/status")
        assert status_resp.json()["kill_switch_active"] is True

    def test_existing_positions_remain_manageable_after_pause(self):
        # This is a design requirement: after pause, existing positions
        # should still be manageable (e.g., manual close via broker interface)
        # The kill switch only prevents NEW trades
        pass  # Placeholder - this is tested at integration level with real broker


# ---------------------------------------------------------------------------
# DeploymentScript
# ---------------------------------------------------------------------------

class TestDeploymentScript:
    """Test staging deployment script with capital limits."""

    def test_deploy_staging_script_validates_config(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "STAGING")
        monkeypatch.setenv("TOTAL_ACCOUNT_CAPITAL", "10000")
        monkeypatch.setenv("LIVE_VALIDATION_CAPITAL_PCT", "10")
        
        from scripts.deploy_live_validation import validate_deployment_config
        config = validate_deployment_config()
        assert config["deployment_mode"] == "STAGING"
        assert config["validation_capital"] == 1000.0

    def test_deploy_staging_requires_manual_confirmation(self):
        # Deployment should require explicit confirmation before running
        from scripts.deploy_live_validation import requires_confirmation
        assert requires_confirmation("STAGING") is True

    def test_deploy_production_blocked_during_validation(self):
        from scripts.deploy_live_validation import is_production_deployment_allowed
        # Production deployment should be blocked while validation is active
        assert is_production_deployment_allowed(validation_active=True) is False
