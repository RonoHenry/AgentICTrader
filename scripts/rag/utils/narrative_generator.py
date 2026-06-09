"""
Narrative Generator for trading setup descriptions.

Generates human-readable narratives from enriched setup data
following the ICT 3-question framework:
1. Where has price come from? (HTF context)
2. Where is it now? (session/time window)
3. Where is it likely to go? (PD arrays, structure)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from scripts.rag.utils.setup_enricher import EnrichedSetup


class NarrativeGenerator:
    """
    Template-based narrative generator for enriched trading setups.

    Generates setup narratives suitable for embedding into a vector store.
    """

    MIN_NARRATIVE_LENGTH = 50

    REQUIRED_KEYWORDS_BY_BIAS = {
        "BULLISH": ["bullish", "buy", "long", "above"],
        "BEARISH": ["bearish", "sell", "short", "below"],
        "NEUTRAL": ["neutral", "range", "consolidat"],
    }

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    def generate_from_setup(self, setup: "EnrichedSetup") -> str:
        """Generate narrative from an EnrichedSetup instance."""
        # Build each sentence component
        session_ctx = self._format_session(setup.time_window, setup.narrative_phase)
        htf_ctx = self._format_htf(
            setup.instrument,
            setup.htf_open_bias,
            setup.htf_timeframe,
            setup.htf_open,
        )
        structure_ctx = self._format_pd_arrays(setup)
        outcome_ctx = self._format_outcome(setup.outcome_result, setup.r_multiple)
        entry_ctx = (
            f"{setup.direction} entry at {setup.entry_price:.5f} "
            f"(SL: {setup.stop_loss:.5f}, TP: {setup.take_profit:.5f})."
        )

        parts = [session_ctx, htf_ctx, structure_ctx, entry_ctx, outcome_ctx]
        return " ".join(p for p in parts if p)

    def generate_from_components(
        self,
        trade: Dict[str, Any],
        htf_context: Dict[str, Any],
        pd_arrays: Dict[str, Any],
        time_context: Dict[str, Any],
        outcome: Dict[str, Any],
    ) -> str:
        """Generate narrative from raw component dicts."""
        instrument = trade.get("instrument", "UNKNOWN")
        direction = trade.get("direction", "UNKNOWN")

        htf_bias = htf_context.get("htf_open_bias", "NEUTRAL")
        htf_open = htf_context.get("htf_open", 0.0)
        htf_timeframe = htf_context.get("htf_timeframe", "H1")
        time_window = time_context.get("time_window", "UNKNOWN")
        narrative_phase = time_context.get("narrative_phase", "UNKNOWN")

        bos = pd_arrays.get("bos_detected", False)
        fvg = pd_arrays.get("fvg_present", False)
        liq = pd_arrays.get("liquidity_sweep", False)
        choch = pd_arrays.get("choch_detected", False)

        outcome_result = outcome.get("outcome_result", "UNKNOWN")
        r_multiple = outcome.get("r_multiple", 0.0)

        session_ctx = self._format_session(time_window, narrative_phase)
        htf_ctx = self._format_htf(instrument, htf_bias, htf_timeframe, htf_open)

        # Build structure string from dict
        structure_parts = []
        if bos:
            structure_parts.append("BOS detected")
        if choch:
            structure_parts.append("CHoCH detected")
        if fvg:
            structure_parts.append("FVG present")
        if liq:
            structure_parts.append("liquidity sweep")

        structure_ctx = (
            "Structure: " + ", ".join(structure_parts) + "."
            if structure_parts
            else "No significant structure detected."
        )

        entry_ctx = f"{direction} trade on {instrument}."
        outcome_ctx = self._format_outcome(outcome_result, r_multiple)

        parts = [session_ctx, htf_ctx, structure_ctx, entry_ctx, outcome_ctx]
        return " ".join(p for p in parts if p)

    def validate_narrative(self, narrative: str) -> Tuple[bool, List[str]]:
        """Validate narrative meets quality standards.

        Returns:
            (is_valid, list_of_errors)
        """
        errors: List[str] = []

        if not narrative or len(narrative) < self.MIN_NARRATIVE_LENGTH:
            errors.append(
                f"Narrative too short: {len(narrative)} chars "
                f"(min {self.MIN_NARRATIVE_LENGTH})."
            )

        return (len(errors) == 0), errors

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    def _format_session(self, time_window: str, narrative_phase: str) -> str:
        """Format session/time context sentence."""
        window_label = time_window.replace("_", " ").title()
        phase_label = narrative_phase.capitalize()
        return f"During the {window_label} ({phase_label} phase),"

    def _format_htf(
        self,
        instrument: str,
        htf_bias: str,
        htf_timeframe: str,
        htf_open: float,
    ) -> str:
        """Format HTF bias context sentence."""
        bias_lower = htf_bias.lower()
        if htf_bias == "BULLISH":
            position_word = "above"
        elif htf_bias == "BEARISH":
            position_word = "below"
        else:
            position_word = "at"

        return (
            f"{instrument} is in a {bias_lower} HTF bias "
            f"{position_word} {htf_timeframe} open at {htf_open:.5f}."
        )

    def _format_pd_arrays(self, setup: "EnrichedSetup") -> str:
        """Format PD array context into readable text."""
        parts: List[str] = []

        if setup.bos_detected:
            parts.append("BOS detected")
        if setup.choch_detected:
            parts.append("CHoCH detected")
        if setup.fvg_present:
            parts.append("FVG present")
        if setup.liquidity_sweep:
            parts.append("liquidity sweep")

        if parts:
            return "Structure context: " + ", ".join(parts) + "."
        return "No significant structure detected."

    def _format_outcome(self, outcome_result: str, r_multiple: float) -> str:
        """Format outcome sentence."""
        return (
            f"Trade resulted in {outcome_result} with {r_multiple:.1f}R."
        )
