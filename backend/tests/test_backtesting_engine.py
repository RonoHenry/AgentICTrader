"""
Test suite for the backtesting engine.

Tests cover:
- Property: no trade uses future data (look-ahead bias check)
- Property: position size never exceeds 1% risk given any SL distance
- Confidence threshold gating (< 0.65 discard, 0.65–0.74 log only, >= 0.75 simulate)
- BacktestResult contains all required metrics

**Validates: Requirements FR-7, NFR-3**
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional

import pytest
from hypothesis import given, strategies as st, assume, settings as h_settings

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `ml` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from ml.backtesting.engine import (  # noqa: E402
    BacktestEngine,
    BacktestResult,
    Setup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_setup(
    confidence_score: float,
    entry_price: float = 1.1000,
    sl_price: float = 1.0950,
    tp_price: float = 1.1100,
    candle_time: Optional[datetime] = None,
    outcome: Optional[str] = None,
) -> Setup:
    """Create a Setup with sensible defaults."""
    if candle_time is None:
        candle_time = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return Setup(
        instrument="EURUSD",
        timeframe="M5",
        candle_time=candle_time,
        confidence_score=confidence_score,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Property-Based Tests
# ---------------------------------------------------------------------------

class TestNoLookAheadBias:
    """
    Property: no trade uses future data.

    For any sequence of setups, the engine must process them in strict
    candle_time order. No trade's processing order should violate the
    temporal ordering of candle_time.

    **Validates: Requirements FR-7 (backtesting integrity)**
    """

    @given(
        n=st.integers(min_value=1, max_value=10),
        confidences=st.lists(
            st.floats(min_value=0.75, max_value=1.0),
            min_size=1,
            max_size=10,
        ),
    )
    @h_settings(max_examples=50)
    def test_trades_processed_in_strict_time_order(self, n: int, confidences: list):
        """
        Property: trades are processed in strict candle_time order (no look-ahead).

        The engine must sort setups by candle_time ascending before processing.
        We verify that the order in which trades appear in results matches
        ascending candle_time order.

        **Validates: Requirements FR-7**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # Create setups with shuffled timestamps (engine must sort them)
        setups = []
        for i, conf in enumerate(confidences):
            # Assign times in reverse order to test that engine sorts them
            candle_time = base_time + timedelta(hours=len(confidences) - i)
            setups.append(make_setup(
                confidence_score=conf,
                candle_time=candle_time,
                outcome="WIN",
            ))

        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run(setups)

        # All simulated trades must have entry_time in ascending order
        if len(result.trades) > 1:
            for i in range(len(result.trades) - 1):
                assert result.trades[i].entry_time <= result.trades[i + 1].entry_time, (
                    f"Trade {i} entry_time {result.trades[i].entry_time} is after "
                    f"trade {i + 1} entry_time {result.trades[i + 1].entry_time} — look-ahead bias!"
                )


class TestPositionSizeRiskLimit:
    """
    Property: position size never exceeds 1% risk given any SL distance.

    For any equity value and any SL distance > 0:
        position_size * sl_distance <= equity * 0.01

    **Validates: Requirements FR-7**
    """

    @given(
        equity=st.floats(min_value=100.0, max_value=1_000_000.0),
        sl_distance=st.floats(min_value=0.0001, max_value=1.0),
    )
    @h_settings(max_examples=100)
    def test_position_size_never_exceeds_1pct_risk(
        self, equity: float, sl_distance: float
    ):
        """
        Property: position_size * sl_distance never exceeds 1% of equity.

        position_size = (equity * risk_pct) / sl_distance
        Therefore: position_size * sl_distance = equity * risk_pct = equity * 0.01

        **Validates: Requirements FR-7**
        """
        assume(sl_distance > 0)
        assume(equity > 0)

        risk_pct = 0.01
        position_size = (equity * risk_pct) / sl_distance
        risk_amount = position_size * sl_distance

        # Risk amount must equal exactly 1% of equity (within floating point tolerance)
        assert risk_amount <= equity * risk_pct + 1e-6, (
            f"Risk amount {risk_amount:.6f} exceeds 1% of equity {equity * risk_pct:.6f}. "
            f"equity={equity}, sl_distance={sl_distance}, position_size={position_size}"
        )

    @given(
        equity=st.floats(min_value=100.0, max_value=1_000_000.0),
        entry_price=st.floats(min_value=0.5, max_value=5.0),
        sl_offset=st.floats(min_value=0.001, max_value=0.5),
    )
    @h_settings(max_examples=100)
    def test_engine_position_size_respects_risk_limit(
        self, equity: float, entry_price: float, sl_offset: float
    ):
        """
        Property: engine-computed position size respects 1% risk limit.

        **Validates: Requirements FR-7**
        """
        assume(entry_price > sl_offset)

        sl_price = entry_price - sl_offset
        tp_price = entry_price + sl_offset * 2  # 2R target

        setup = Setup(
            instrument="EURUSD",
            timeframe="M5",
            candle_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            confidence_score=0.80,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            outcome="WIN",
        )

        engine = BacktestEngine(initial_equity=equity, risk_pct=0.01)
        result = engine.run([setup])

        assert result.trade_count == 1
        trade = result.trades[0]

        sl_distance = abs(entry_price - sl_price)
        risk_amount = trade.position_size * sl_distance

        assert risk_amount <= equity * 0.01 + 1e-6, (
            f"Risk amount {risk_amount:.6f} exceeds 1% of equity {equity * 0.01:.6f}. "
            f"equity={equity}, sl_distance={sl_distance}, position_size={trade.position_size}"
        )


# ---------------------------------------------------------------------------
# Confidence Threshold Unit Tests
# ---------------------------------------------------------------------------

class TestConfidenceThresholds:
    """
    Tests for confidence threshold gating.

    Thresholds (from design.md):
      < 0.65  → DISCARD (no trade, not logged)
      0.65–0.74 → LOG ONLY (no trade simulated)
      >= 0.75 → NOTIFY (trade simulated)
    """

    def test_confidence_below_floor_discards_setup(self):
        """
        Test: confidence < 0.65 → engine discards setup, no trade simulated.

        **Validates: Requirements FR-7**
        """
        setup = make_setup(confidence_score=0.60)
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([setup])

        assert result.trade_count == 0, (
            f"Expected 0 trades for confidence=0.60, got {result.trade_count}"
        )
        # Discarded setups should not appear in log_only_setups
        assert len(result.log_only_setups) == 0

    def test_confidence_at_floor_discards_setup(self):
        """
        Test: confidence = 0.64 (just below floor) → discarded.

        **Validates: Requirements FR-7**
        """
        setup = make_setup(confidence_score=0.64)
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([setup])

        assert result.trade_count == 0

    def test_confidence_in_log_only_range_no_trade(self):
        """
        Test: confidence 0.65–0.74 → logged but no trade simulated.

        **Validates: Requirements FR-7**
        """
        setup = make_setup(confidence_score=0.70)
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([setup])

        assert result.trade_count == 0, (
            f"Expected 0 trades for confidence=0.70 (log-only), got {result.trade_count}"
        )
        # Should appear in log_only_setups
        assert len(result.log_only_setups) == 1, (
            f"Expected 1 log-only setup for confidence=0.70, got {len(result.log_only_setups)}"
        )

    def test_confidence_at_log_only_boundary_no_trade(self):
        """
        Test: confidence = 0.65 (at log-only floor) → logged, no trade.

        **Validates: Requirements FR-7**
        """
        setup = make_setup(confidence_score=0.65)
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([setup])

        assert result.trade_count == 0
        assert len(result.log_only_setups) == 1

    def test_confidence_at_notify_threshold_simulates_trade(self):
        """
        Test: confidence >= 0.75 → trade simulated.

        **Validates: Requirements FR-7**
        """
        setup = make_setup(confidence_score=0.75, outcome="WIN")
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([setup])

        assert result.trade_count == 1, (
            f"Expected 1 trade for confidence=0.75, got {result.trade_count}"
        )

    def test_confidence_above_notify_threshold_simulates_trade(self):
        """
        Test: confidence = 0.85 (auto-execute threshold) → trade simulated.

        **Validates: Requirements FR-7**
        """
        setup = make_setup(confidence_score=0.85, outcome="WIN")
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([setup])

        assert result.trade_count == 1


# ---------------------------------------------------------------------------
# BacktestResult Metrics Tests
# ---------------------------------------------------------------------------

class TestBacktestResultMetrics:
    """
    Tests that BacktestResult contains all required metrics.
    """

    def test_backtest_result_has_all_required_fields(self):
        """
        Test: BacktestResult dataclass has all required fields.

        Required: sharpe_ratio, sortino_ratio, max_drawdown_pct, win_rate,
                  avg_r_multiple, expectancy, trade_count, total_pnl.

        **Validates: Requirements NFR-3**
        """
        # Create a mix of winning and losing setups
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        setups = [
            make_setup(
                confidence_score=0.80,
                entry_price=1.1000,
                sl_price=1.0950,
                tp_price=1.1100,
                candle_time=base_time + timedelta(hours=i),
                outcome="WIN" if i % 2 == 0 else "LOSS",
            )
            for i in range(6)
        ]

        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run(setups)

        # Verify all required fields exist
        assert hasattr(result, "sharpe_ratio"), "BacktestResult missing sharpe_ratio"
        assert hasattr(result, "sortino_ratio"), "BacktestResult missing sortino_ratio"
        assert hasattr(result, "max_drawdown_pct"), "BacktestResult missing max_drawdown_pct"
        assert hasattr(result, "win_rate"), "BacktestResult missing win_rate"
        assert hasattr(result, "avg_r_multiple"), "BacktestResult missing avg_r_multiple"
        assert hasattr(result, "expectancy"), "BacktestResult missing expectancy"
        assert hasattr(result, "trade_count"), "BacktestResult missing trade_count"
        assert hasattr(result, "total_pnl"), "BacktestResult missing total_pnl"

    def test_backtest_result_metrics_computed_correctly(self):
        """
        Test: run engine on known setups → metrics are computed correctly.

        Uses 4 WIN trades and 2 LOSS trades with known R-multiples.

        **Validates: Requirements NFR-3**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # 4 wins, 2 losses — all with 2R target (tp = entry + 2 * (entry - sl))
        setups = []
        for i in range(4):
            setups.append(make_setup(
                confidence_score=0.80,
                entry_price=1.1000,
                sl_price=1.0950,   # SL distance = 0.005
                tp_price=1.1100,   # TP distance = 0.010 → 2R
                candle_time=base_time + timedelta(hours=i),
                outcome="WIN",
            ))
        for i in range(2):
            setups.append(make_setup(
                confidence_score=0.80,
                entry_price=1.1000,
                sl_price=1.0950,
                tp_price=1.1100,
                candle_time=base_time + timedelta(hours=4 + i),
                outcome="LOSS",
            ))

        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run(setups)

        assert result.trade_count == 6
        assert result.win_rate == pytest.approx(4 / 6, abs=0.01)
        # avg_r_multiple: 4 wins at +2R, 2 losses at -1R → (4*2 + 2*(-1)) / 6 = 1.0
        assert result.avg_r_multiple == pytest.approx(1.0, abs=0.01)
        # max_drawdown_pct must be >= 0
        assert result.max_drawdown_pct >= 0.0
        # total_pnl should be positive (4 wins at 2R vs 2 losses at 1R)
        assert result.total_pnl > 0

    def test_backtest_result_all_losses(self):
        """
        Test: all-loss scenario → win_rate=0, total_pnl < 0.

        **Validates: Requirements NFR-3**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        setups = [
            make_setup(
                confidence_score=0.80,
                candle_time=base_time + timedelta(hours=i),
                outcome="LOSS",
            )
            for i in range(3)
        ]

        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run(setups)

        assert result.trade_count == 3
        assert result.win_rate == pytest.approx(0.0, abs=0.001)
        assert result.total_pnl < 0

    def test_backtest_result_all_wins(self):
        """
        Test: all-win scenario → win_rate=1.0, total_pnl > 0.

        **Validates: Requirements NFR-3**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        setups = [
            make_setup(
                confidence_score=0.80,
                candle_time=base_time + timedelta(hours=i),
                outcome="WIN",
            )
            for i in range(3)
        ]

        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run(setups)

        assert result.trade_count == 3
        assert result.win_rate == pytest.approx(1.0, abs=0.001)
        assert result.total_pnl > 0

    def test_backtest_result_empty_setups(self):
        """
        Test: no setups → all metrics are zero/default.

        **Validates: Requirements NFR-3**
        """
        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run([])

        assert result.trade_count == 0
        assert result.win_rate == 0.0
        assert result.total_pnl == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.sortino_ratio == 0.0
        assert result.max_drawdown_pct == 0.0

    def test_sharpe_and_sortino_returned(self):
        """
        Test: Sharpe and Sortino ratios are returned (numeric values).

        **Validates: Requirements NFR-3**
        """
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        setups = [
            make_setup(
                confidence_score=0.80,
                candle_time=base_time + timedelta(hours=i),
                outcome="WIN" if i % 3 != 0 else "LOSS",
            )
            for i in range(9)
        ]

        engine = BacktestEngine(initial_equity=10_000.0)
        result = engine.run(setups)

        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.sortino_ratio, float)
        # Ratios can be positive or negative but must be finite
        assert result.sharpe_ratio == result.sharpe_ratio  # not NaN
        assert result.sortino_ratio == result.sortino_ratio  # not NaN
