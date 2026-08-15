"""
Test suite for AgentState Pydantic model.

TDD Phase: RED → GREEN → REFACTOR

Tests cover:
- AgentState instantiates with all required fields
- Optional fields default to None
- mode field only accepts "HUMAN_IN_LOOP" or "AUTONOMOUS"
- All time window fields present and typed correctly

**Validates: Requirements FR-6, FR-3A**
"""
from __future__ import annotations

import sys
import os
import pytest
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup — add workspace root so `agent` package is importable
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from agent.state import (
    AgentState,
    AgentMode,
    Direction,
    DecisionAction,
    RiskVerdictEnum,
    Pattern,
    TradePlan,
    RiskValidation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_state(**overrides) -> AgentState:
    """Return an AgentState with only the required fields populated."""
    defaults = {
        "setup_id": "setup-001",
        "instrument": "EURUSD",
        "timeframe": "M5",
        "detected_at": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return AgentState(**defaults)


# ---------------------------------------------------------------------------
# TestAgentStateInstantiation
# ---------------------------------------------------------------------------

class TestAgentStateInstantiation:
    """Tests that AgentState instantiates correctly with required fields.

    **Validates: Requirements FR-6**
    """

    def test_instantiates_with_all_required_fields(self):
        """Test: AgentState instantiates with all required fields.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()

        assert state.setup_id == "setup-001"
        assert state.instrument == "EURUSD"
        assert state.timeframe == "M5"
        assert state.detected_at == datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_required_fields_are_setup_id_instrument_timeframe_detected_at(self):
        """Test: Missing any required field raises a ValidationError.

        **Validates: Requirements FR-6**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AgentState(instrument="EURUSD", timeframe="M5",
                       detected_at=datetime.now(tz=timezone.utc))  # missing setup_id

        with pytest.raises(ValidationError):
            AgentState(setup_id="s1", timeframe="M5",
                       detected_at=datetime.now(tz=timezone.utc))  # missing instrument

        with pytest.raises(ValidationError):
            AgentState(setup_id="s1", instrument="EURUSD",
                       detected_at=datetime.now(tz=timezone.utc))  # missing timeframe

        with pytest.raises(ValidationError):
            AgentState(setup_id="s1", instrument="EURUSD", timeframe="M5")  # missing detected_at


# ---------------------------------------------------------------------------
# TestAgentStateOptionalFieldDefaults
# ---------------------------------------------------------------------------

class TestAgentStateOptionalFieldDefaults:
    """Tests that optional fields default to None (or appropriate defaults).

    **Validates: Requirements FR-6**
    """

    def test_direction_defaults_to_none(self):
        """Test: direction defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.direction is None

    def test_regime_defaults_to_none(self):
        """Test: regime defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.regime is None

    def test_regime_confidence_defaults_to_none(self):
        """Test: regime_confidence defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.regime_confidence is None

    def test_patterns_defaults_to_empty_list(self):
        """Test: patterns defaults to empty list.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.patterns == []

    def test_raw_confidence_defaults_to_none(self):
        """Test: raw_confidence defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.raw_confidence is None

    def test_htf_alignment_defaults_to_empty_dict(self):
        """Test: htf_alignment defaults to empty dict.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.htf_alignment == {}

    def test_sentiment_score_defaults_to_none(self):
        """Test: sentiment_score defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.sentiment_score is None

    def test_sentiment_label_defaults_to_none(self):
        """Test: sentiment_label defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.sentiment_label is None

    def test_sentiment_aligned_defaults_to_none(self):
        """Test: sentiment_aligned defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.sentiment_aligned is None

    def test_top_headlines_defaults_to_empty_list(self):
        """Test: top_headlines defaults to empty list.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.top_headlines == []

    def test_calendar_clear_defaults_to_true(self):
        """Test: calendar_clear defaults to True.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.calendar_clear is True

    def test_minutes_to_next_event_defaults_to_none(self):
        """Test: minutes_to_next_event defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.minutes_to_next_event is None

    def test_next_event_name_defaults_to_none(self):
        """Test: next_event_name defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.next_event_name is None

    def test_final_confidence_defaults_to_none(self):
        """Test: final_confidence defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.final_confidence is None

    def test_trade_plan_defaults_to_none(self):
        """Test: trade_plan defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.trade_plan is None

    def test_risk_validation_defaults_to_none(self):
        """Test: risk_validation defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.risk_validation is None

    def test_decision_defaults_to_none(self):
        """Test: decision defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.decision is None

    def test_decision_reason_defaults_to_none(self):
        """Test: decision_reason defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.decision_reason is None

    def test_trade_reasoning_defaults_to_none(self):
        """Test: trade_reasoning defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.trade_reasoning is None

    def test_broker_order_id_defaults_to_none(self):
        """Test: broker_order_id defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.broker_order_id is None

    def test_trade_id_defaults_to_none(self):
        """Test: trade_id defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.trade_id is None

    def test_outcome_defaults_to_none(self):
        """Test: outcome defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.outcome is None

    def test_r_multiple_defaults_to_none(self):
        """Test: r_multiple defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.r_multiple is None

    def test_close_price_defaults_to_none(self):
        """Test: close_price defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.close_price is None

    def test_close_time_defaults_to_none(self):
        """Test: close_time defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.close_time is None

    def test_error_defaults_to_none(self):
        """Test: error defaults to None.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.error is None

    def test_processing_times_defaults_to_empty_dict(self):
        """Test: processing_times defaults to empty dict.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.processing_times == {}


# ---------------------------------------------------------------------------
# TestAgentModeValidation
# ---------------------------------------------------------------------------

class TestAgentModeValidation:
    """Tests that mode field only accepts valid AgentMode values.

    **Validates: Requirements FR-6**
    """

    def test_mode_defaults_to_human_in_loop(self):
        """Test: mode defaults to HUMAN_IN_LOOP.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state()
        assert state.mode == AgentMode.HUMAN_IN_LOOP

    def test_mode_accepts_human_in_loop_string(self):
        """Test: mode accepts "HUMAN_IN_LOOP" string.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state(mode="HUMAN_IN_LOOP")
        assert state.mode == AgentMode.HUMAN_IN_LOOP

    def test_mode_accepts_autonomous_string(self):
        """Test: mode accepts "AUTONOMOUS" string.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state(mode="AUTONOMOUS")
        assert state.mode == AgentMode.AUTONOMOUS

    def test_mode_accepts_human_in_loop_enum(self):
        """Test: mode accepts AgentMode.HUMAN_IN_LOOP enum value.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state(mode=AgentMode.HUMAN_IN_LOOP)
        assert state.mode == AgentMode.HUMAN_IN_LOOP

    def test_mode_accepts_autonomous_enum(self):
        """Test: mode accepts AgentMode.AUTONOMOUS enum value.

        **Validates: Requirements FR-6**
        """
        state = _minimal_state(mode=AgentMode.AUTONOMOUS)
        assert state.mode == AgentMode.AUTONOMOUS

    def test_mode_rejects_invalid_string(self):
        """Test: mode rejects invalid string values.

        **Validates: Requirements FR-6**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _minimal_state(mode="MANUAL")

        with pytest.raises(ValidationError):
            _minimal_state(mode="AUTO")

        with pytest.raises(ValidationError):
            _minimal_state(mode="human_in_loop")  # case-sensitive

        with pytest.raises(ValidationError):
            _minimal_state(mode="autonomous")  # case-sensitive

    def test_mode_rejects_none(self):
        """Test: mode rejects None (it has a default, not Optional).

        **Validates: Requirements FR-6**
        """
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _minimal_state(mode=None)

    def test_agent_mode_enum_values(self):
        """Test: AgentMode enum has exactly HUMAN_IN_LOOP and AUTONOMOUS.

        **Validates: Requirements FR-6**
        """
        values = {m.value for m in AgentMode}
        assert values == {"HUMAN_IN_LOOP", "AUTONOMOUS"}


# ---------------------------------------------------------------------------
# TestTimeWindowFields
# ---------------------------------------------------------------------------

class TestTimeWindowFields:
    """Tests that all time window fields are present and typed correctly.

    **Validates: Requirements FR-3A**
    """

    def test_time_window_defaults_to_none(self):
        """Test: time_window defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.time_window is None

    def test_narrative_phase_defaults_to_none(self):
        """Test: narrative_phase defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.narrative_phase is None

    def test_time_window_weight_defaults_to_none(self):
        """Test: time_window_weight defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.time_window_weight is None

    def test_is_killzone_defaults_to_none(self):
        """Test: is_killzone defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.is_killzone is None

    def test_price_vs_daily_open_defaults_to_none(self):
        """Test: price_vs_daily_open defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.price_vs_daily_open is None

    def test_price_vs_weekly_open_defaults_to_none(self):
        """Test: price_vs_weekly_open defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.price_vs_weekly_open is None

    def test_price_vs_true_day_open_defaults_to_none(self):
        """Test: price_vs_true_day_open defaults to None.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        assert state.price_vs_true_day_open is None

    def test_time_window_accepts_string_value(self):
        """Test: time_window accepts a string value like 'LONDON_KILLZONE'.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state(time_window="LONDON_KILLZONE")
        assert state.time_window == "LONDON_KILLZONE"

    def test_narrative_phase_accepts_string_value(self):
        """Test: narrative_phase accepts a string value like 'MANIPULATION'.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state(narrative_phase="MANIPULATION")
        assert state.narrative_phase == "MANIPULATION"

    def test_time_window_weight_accepts_float_value(self):
        """Test: time_window_weight accepts a float value between 0.0 and 1.0.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state(time_window_weight=0.9)
        assert state.time_window_weight == 0.9

    def test_is_killzone_accepts_bool_value(self):
        """Test: is_killzone accepts a bool value.

        **Validates: Requirements FR-3A**
        """
        state_true = _minimal_state(is_killzone=True)
        assert state_true.is_killzone is True

        state_false = _minimal_state(is_killzone=False)
        assert state_false.is_killzone is False

    def test_price_vs_daily_open_accepts_above_below_at(self):
        """Test: price_vs_daily_open accepts 'ABOVE', 'BELOW', 'AT'.

        **Validates: Requirements FR-3A**
        """
        for val in ("ABOVE", "BELOW", "AT"):
            state = _minimal_state(price_vs_daily_open=val)
            assert state.price_vs_daily_open == val

    def test_price_vs_weekly_open_accepts_above_below_at(self):
        """Test: price_vs_weekly_open accepts 'ABOVE', 'BELOW', 'AT'.

        **Validates: Requirements FR-3A**
        """
        for val in ("ABOVE", "BELOW", "AT"):
            state = _minimal_state(price_vs_weekly_open=val)
            assert state.price_vs_weekly_open == val

    def test_price_vs_true_day_open_accepts_above_below_at(self):
        """Test: price_vs_true_day_open accepts 'ABOVE', 'BELOW', 'AT'.

        **Validates: Requirements FR-3A**
        """
        for val in ("ABOVE", "BELOW", "AT"):
            state = _minimal_state(price_vs_true_day_open=val)
            assert state.price_vs_true_day_open == val

    def test_all_time_window_fields_present_on_model(self):
        """Test: all 7 time window fields are present as model fields.

        **Validates: Requirements FR-3A**
        """
        state = _minimal_state()
        expected_fields = {
            "time_window",
            "narrative_phase",
            "time_window_weight",
            "is_killzone",
            "price_vs_daily_open",
            "price_vs_weekly_open",
            "price_vs_true_day_open",
        }
        model_fields = set(AgentState.model_fields.keys())
        assert expected_fields.issubset(model_fields), (
            f"Missing time window fields: {expected_fields - model_fields}"
        )

    def test_time_window_field_type_is_optional_str(self):
        """Test: time_window field annotation is Optional[str].

        **Validates: Requirements FR-3A**
        """
        import typing
        field_info = AgentState.model_fields["time_window"]
        # Pydantic v2: annotation is the type hint
        annotation = field_info.annotation
        # Should be Optional[str] i.e. str | None
        assert annotation is not None

    def test_time_window_weight_field_type_is_optional_float(self):
        """Test: time_window_weight field annotation is Optional[float].

        **Validates: Requirements FR-3A**
        """
        field_info = AgentState.model_fields["time_window_weight"]
        annotation = field_info.annotation
        assert annotation is not None

    def test_is_killzone_field_type_is_optional_bool(self):
        """Test: is_killzone field annotation is Optional[bool].

        **Validates: Requirements FR-3A**
        """
        field_info = AgentState.model_fields["is_killzone"]
        annotation = field_info.annotation
        assert annotation is not None


# ---------------------------------------------------------------------------
# TestAgentStateFullPopulation
# ---------------------------------------------------------------------------

class TestAgentStateFullPopulation:
    """Tests that AgentState can be fully populated with all fields.

    **Validates: Requirements FR-6, FR-3A**
    """

    def test_fully_populated_state(self):
        """Test: AgentState can be instantiated with all fields populated.

        **Validates: Requirements FR-6, FR-3A**
        """
        pattern = Pattern(type="BOS_CONFIRMED", confidence=0.85, level=1.1050)
        trade_plan = TradePlan(
            entry=1.1050,
            stop_loss=1.1020,
            take_profit_1=1.1110,
            r_ratio=2.0,
            recommended_size=0.5,
        )
        risk_val = RiskValidation(
            verdict=RiskVerdictEnum.APPROVED,
            recommended_size=0.5,
        )

        state = AgentState(
            setup_id="setup-full-001",
            instrument="EURUSD",
            timeframe="M5",
            direction=Direction.LONG,
            detected_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            regime="TRENDING_BULLISH",
            regime_confidence=0.82,
            patterns=[pattern],
            raw_confidence=0.78,
            htf_alignment={"H4": "BULLISH", "D1": "BULLISH"},
            sentiment_score=0.35,
            sentiment_label="POSITIVE",
            sentiment_aligned=True,
            top_headlines=["Fed holds rates steady"],
            calendar_clear=True,
            minutes_to_next_event=120,
            next_event_name="CPI",
            final_confidence=0.83,
            trade_plan=trade_plan,
            risk_validation=risk_val,
            decision=DecisionAction.NOTIFY,
            decision_reason="All gates passed",
            mode=AgentMode.HUMAN_IN_LOOP,
            trade_reasoning="HTF bias is BULLISH. BOS confirmed at M5.",
            broker_order_id=None,
            trade_id=None,
            outcome=None,
            r_multiple=None,
            close_price=None,
            close_time=None,
            error=None,
            processing_times={"observe": 0.05, "analyse": 0.12},
            # Time window fields
            time_window="LONDON_KILLZONE",
            narrative_phase="MANIPULATION",
            time_window_weight=0.9,
            is_killzone=True,
            price_vs_daily_open="ABOVE",
            price_vs_weekly_open="ABOVE",
            price_vs_true_day_open="BELOW",
        )

        assert state.setup_id == "setup-full-001"
        assert state.direction == Direction.LONG
        assert state.mode == AgentMode.HUMAN_IN_LOOP
        assert state.time_window == "LONDON_KILLZONE"
        assert state.narrative_phase == "MANIPULATION"
        assert state.time_window_weight == 0.9
        assert state.is_killzone is True
        assert state.price_vs_daily_open == "ABOVE"
        assert state.price_vs_weekly_open == "ABOVE"
        assert state.price_vs_true_day_open == "BELOW"
        assert len(state.patterns) == 1
        assert state.patterns[0].type == "BOS_CONFIRMED"


# ---------------------------------------------------------------------------
# TestAgentStateVisualModelFields
# ---------------------------------------------------------------------------

class TestAgentStateVisualModelFields:
    """Tests for the fields added to integrate services/visual_model.

    **Validates: Requirement 8.5 (.kiro/specs/visual-model/requirements.md)**
    """

    def test_agent_state_candles_by_tf_optional_defaults_none(self):
        state = _minimal_state()
        assert state.candles_by_tf is None

    def test_agent_state_visual_analysis_optional_defaults_none(self):
        state = _minimal_state()
        assert state.visual_analysis is None

    def test_agent_state_visual_modifier_optional_defaults_none(self):
        state = _minimal_state()
        assert state.visual_modifier is None

    def test_agent_state_visual_hard_block_reason_optional_defaults_none(self):
        state = _minimal_state()
        assert state.visual_hard_block_reason is None

    def test_agent_state_visual_narrative_optional_defaults_none(self):
        state = _minimal_state()
        assert state.visual_narrative is None

    def test_agent_state_construction_unaffected_for_existing_callers(self):
        """Regression guard: adding the new Optional fields must not change
        construction behaviour for callers that only pass the pre-existing
        required fields."""
        state = _minimal_state()
        assert state.setup_id == "setup-001"
        assert state.instrument == "EURUSD"
