"""Tests for narrative generation."""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from scripts.rag.utils.narrative_generator import NarrativeGenerator
from scripts.rag.utils.setup_enricher import EnrichedSetup
from datetime import datetime, timezone
from hypothesis import given, strategies as st, assume


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_enriched_setup(**overrides) -> EnrichedSetup:
    defaults = {
        "trade_id": "TRD-001",
        "timestamp": datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc),
        "instrument": "EURUSD",
        "direction": "BUY",
        "entry_price": 1.5050,
        "exit_price": 1.5150,
        "stop_loss": 1.4950,
        "take_profit": 1.5200,
        "r_multiple": 2.0,
        "outcome_result": "WIN",
        "htf_timeframe": "H1",
        "htf_open": 1.5000,
        "htf_high": 1.5200,
        "htf_low": 1.4900,
        "htf_open_bias": "BULLISH",
        "htf_high_proximity_pct": 50.0,
        "htf_low_proximity_pct": 50.0,
        "htf_body_pct": 60.0,
        "htf_close_position": 60.0,
        "bos_detected": True,
        "choch_detected": False,
        "fvg_present": True,
        "liquidity_sweep": False,
        "swing_high_distance": 0.015,
        "swing_low_distance": 0.010,
        "htf_trend_bias": "BULLISH",
        "time_window": "LONDON_KILLZONE",
        "narrative_phase": "MANIPULATION",
        "time_window_weight": 0.9,
        "is_killzone": True,
        "narrative": "",
        "confluence_count": 3,
    }
    defaults.update(overrides)
    return EnrichedSetup(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNarrativeGenerator:
    def test_narrative_is_non_empty_string(self):
        """Generated narrative is a non-empty string."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup()
        narrative = gen.generate_from_setup(setup)
        assert isinstance(narrative, str)
        assert len(narrative) > 50

    def test_narrative_contains_instrument(self):
        """Generated narrative mentions the instrument."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup(instrument="GBPUSD")
        narrative = gen.generate_from_setup(setup)
        assert "GBPUSD" in narrative

    def test_narrative_contains_htf_bias(self):
        """Narrative mentions HTF bias direction."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup(htf_open_bias="BULLISH")
        narrative = gen.generate_from_setup(setup)
        assert any(
            word in narrative.lower() for word in ["bullish", "buy", "long", "above"]
        )

    def test_narrative_contains_time_window(self):
        """Narrative mentions the time window/session."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup(time_window="LONDON_KILLZONE")
        narrative = gen.generate_from_setup(setup)
        assert any(
            word in narrative.lower() for word in ["london", "killzone", "session"]
        )

    def test_narrative_quality_validation_min_length(self):
        """Narrative passes quality validation with minimum length."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup()
        narrative = gen.generate_from_setup(setup)
        is_valid, errors = gen.validate_narrative(narrative)
        assert is_valid, f"Narrative failed validation: {errors}"

    def test_narrative_contains_outcome(self):
        """Narrative mentions the outcome (WIN/LOSS)."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup(outcome_result="WIN", r_multiple=2.5)
        narrative = gen.generate_from_setup(setup)
        assert any(
            word in narrative.lower() for word in ["win", "profit", "r", "2.5", "2R"]
        )

    def test_narrative_bearish_setup(self):
        """Bearish setup generates appropriate narrative."""
        gen = NarrativeGenerator()
        setup = make_enriched_setup(
            direction="SELL",
            htf_open_bias="BEARISH",
            htf_trend_bias="BEARISH",
            outcome_result="WIN",
        )
        narrative = gen.generate_from_setup(setup)
        assert any(
            word in narrative.lower() for word in ["bearish", "sell", "short", "below"]
        )

    def test_validate_narrative_fails_for_empty_string(self):
        """Narrative validation fails for empty or too-short strings."""
        gen = NarrativeGenerator()
        is_valid, errors = gen.validate_narrative("")
        assert not is_valid
        assert len(errors) > 0

    def test_generate_from_components_produces_valid_narrative(self):
        """generate_from_components can produce narrative from raw trade+feature dicts."""
        gen = NarrativeGenerator()
        trade = {
            "trade_id": "TRD-001",
            "instrument": "EURUSD",
            "direction": "BUY",
        }
        htf_context = {
            "htf_open_bias": "BULLISH",
            "htf_open": 1.5000,
            "htf_high": 1.5200,
            "htf_low": 1.4900,
        }
        pd_arrays = {
            "bos_detected": True,
            "fvg_present": True,
            "liquidity_sweep": False,
        }
        time_context = {
            "time_window": "LONDON_KILLZONE",
            "narrative_phase": "MANIPULATION",
        }
        outcome = {"outcome_result": "WIN", "r_multiple": 2.0}

        narrative = gen.generate_from_components(
            trade, htf_context, pd_arrays, time_context, outcome
        )
        assert isinstance(narrative, str)
        assert len(narrative) > 50
