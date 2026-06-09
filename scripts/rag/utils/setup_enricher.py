"""
Setup Enricher — enriches raw trade records with HTF structure,
PD arrays, and session context using existing ML feature extractors.

Usage:
    enricher = SetupEnricher(htf_timeframe="H1")
    result = enricher.enrich(trade, candles, htf_candles)
"""
from __future__ import annotations

import sys
import os

# Ensure workspace root is importable
_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, _WORKSPACE_ROOT)

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ml.features.htf_projections import HTFProjectionExtractor
from ml.features.zone_features import ZoneFeatureExtractor
from ml.features.session_features import TimeWindowClassifier
from scripts.rag.utils.narrative_generator import NarrativeGenerator


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class EnrichedSetup(BaseModel):
    """Enriched trade setup with HTF/PD array/session context."""

    trade_id: str
    timestamp: datetime
    instrument: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    r_multiple: float
    outcome_result: str  # "WIN" or "LOSS"

    # HTF context
    htf_timeframe: str
    htf_open: float
    htf_high: float
    htf_low: float
    htf_open_bias: str  # BULLISH / BEARISH / NEUTRAL
    htf_high_proximity_pct: float
    htf_low_proximity_pct: float
    htf_body_pct: float
    htf_close_position: float

    # PD array context
    bos_detected: bool
    choch_detected: bool
    fvg_present: bool
    liquidity_sweep: bool
    swing_high_distance: float
    swing_low_distance: float
    htf_trend_bias: str

    # Session context
    time_window: str  # e.g. LONDON_KILLZONE
    narrative_phase: str  # e.g. MANIPULATION
    time_window_weight: float
    is_killzone: bool

    # Narrative
    narrative: str

    # Confluence count (derived)
    confluence_count: int

    # Full setup for storage
    full_setup: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Enricher
# ---------------------------------------------------------------------------


class SetupEnricher:
    """Enriches raw trade records with HTF structure, PD arrays, and session context."""

    def __init__(self, htf_timeframe: str = "H1"):
        self.htf_extractor = HTFProjectionExtractor()
        self.zone_extractor = ZoneFeatureExtractor()
        self.session_classifier = TimeWindowClassifier()
        self.narrative_gen = NarrativeGenerator()
        self.htf_timeframe = htf_timeframe
        self._htf_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def enrich(
        self,
        trade: Dict[str, Any],
        candles: List[Dict[str, Any]],
        htf_candles: List[Dict[str, Any]],
    ) -> EnrichedSetup:
        """Enrich a single trade with HTF/PD array/session context."""

        # --- Parse scalar fields from nested or flat trade dict ---
        trade_id = trade.get("trade_id", "UNKNOWN")
        instrument = trade.get("instrument", "UNKNOWN")
        direction = trade.get("direction", "BUY")

        entry = trade.get("entry", {})
        entry_price = float(entry.get("price", trade.get("entry_price", 0.0)))
        entry_time_str: str = entry.get("time", trade.get("entry_time", ""))

        exit_ = trade.get("exit", {})
        exit_price = float(exit_.get("price", trade.get("exit_price", 0.0)))

        risk = trade.get("risk", {})
        stop_loss = float(risk.get("stop_loss", trade.get("stop_loss", 0.0)))
        take_profit = float(risk.get("take_profit", trade.get("take_profit", 0.0)))

        outcome = trade.get("outcome", {})
        r_multiple = float(outcome.get("r_multiple", trade.get("r_multiple", 0.0)))

        # Derive outcome result
        outcome_result = trade.get("outcome_result") or outcome.get("outcome_result")
        if outcome_result is None:
            outcome_result = "WIN" if r_multiple > 0 else "LOSS"

        # Parse entry timestamp
        entry_time: datetime = self._parse_timestamp(entry_time_str)

        # --- HTF projection (with caching) ---
        htf_proj = self._get_htf_projection_cached(
            instrument=instrument,
            entry_price=entry_price,
            htf_candles=htf_candles,
            htf_timeframe=self.htf_timeframe,
        )

        # --- Zone / PD array features ---
        htf_candle_for_zone = htf_candles[0] if htf_candles else None
        zone_feats = self.zone_extractor.extract(candles, htf_candle=htf_candle_for_zone)

        # --- Session / time window classification ---
        time_feats = self.session_classifier.classify(
            timestamp_utc=entry_time,
            instrument=instrument,
        )

        # --- Narrative ---
        htf_context = {
            "htf_open_bias": htf_proj.htf_open_bias,
            "htf_open": htf_proj.htf_open,
            "htf_high": htf_proj.htf_high,
            "htf_low": htf_proj.htf_low,
            "htf_timeframe": self.htf_timeframe,
        }
        pd_context = {
            "bos_detected": zone_feats.bos_detected,
            "choch_detected": zone_feats.choch_detected,
            "fvg_present": zone_feats.fvg_present,
            "liquidity_sweep": zone_feats.liquidity_sweep,
        }
        time_context = {
            "time_window": time_feats.time_window,
            "narrative_phase": time_feats.narrative_phase,
        }
        outcome_dict = {
            "outcome_result": outcome_result,
            "r_multiple": r_multiple,
        }
        trade_for_narrative = {
            "trade_id": trade_id,
            "instrument": instrument,
            "direction": direction,
        }
        narrative = self.narrative_gen.generate_from_components(
            trade_for_narrative, htf_context, pd_context, time_context, outcome_dict
        )

        # --- Confluence count ---
        confluence_count = self._compute_confluence_count(htf_proj, zone_feats, time_feats)

        return EnrichedSetup(
            trade_id=trade_id,
            timestamp=entry_time,
            instrument=instrument,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            r_multiple=r_multiple,
            outcome_result=outcome_result,
            # HTF
            htf_timeframe=self.htf_timeframe,
            htf_open=htf_proj.htf_open,
            htf_high=htf_proj.htf_high,
            htf_low=htf_proj.htf_low,
            htf_open_bias=htf_proj.htf_open_bias,
            htf_high_proximity_pct=htf_proj.htf_high_proximity_pct,
            htf_low_proximity_pct=htf_proj.htf_low_proximity_pct,
            htf_body_pct=htf_proj.htf_body_pct,
            htf_close_position=htf_proj.htf_close_position,
            # PD arrays
            bos_detected=zone_feats.bos_detected,
            choch_detected=zone_feats.choch_detected,
            fvg_present=zone_feats.fvg_present,
            liquidity_sweep=zone_feats.liquidity_sweep,
            swing_high_distance=zone_feats.swing_high_distance,
            swing_low_distance=zone_feats.swing_low_distance,
            htf_trend_bias=zone_feats.htf_trend_bias,
            # Session
            time_window=time_feats.time_window,
            narrative_phase=time_feats.narrative_phase,
            time_window_weight=time_feats.time_window_weight,
            is_killzone=time_feats.is_killzone,
            # Narrative & confluence
            narrative=narrative,
            confluence_count=confluence_count,
            full_setup=trade,
        )

    def enrich_batch(
        self, trades_with_candles: List[Dict[str, Any]]
    ) -> List[EnrichedSetup]:
        """Enrich a batch of trades.

        Each item in trades_with_candles must contain:
            - trade: Dict
            - candles: List[Dict]
            - htf_candles: List[Dict]
        """
        results: List[EnrichedSetup] = []
        for item in trades_with_candles:
            enriched = self.enrich(
                item["trade"], item["candles"], item["htf_candles"]
            )
            results.append(enriched)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_htf_projection_cached(
        self,
        instrument: str,
        entry_price: float,
        htf_candles: List[Dict[str, Any]],
        htf_timeframe: str,
    ):
        """Compute HTF projection with caching keyed on symbol/timeframe/candle-time."""
        if htf_candles:
            cache_key = (
                f"{instrument}_{htf_timeframe}_{htf_candles[0].get('time', 'unknown')}"
            )
        else:
            cache_key = f"{instrument}_{htf_timeframe}_no_candles"

        if cache_key not in self._htf_cache:
            self._htf_cache[cache_key] = self.htf_extractor.compute_projections(
                current_price=entry_price,
                htf_candles=htf_candles,
                htf_timeframe=htf_timeframe,
            )
        return self._htf_cache[cache_key]

    def _compute_confluence_count(self, htf_proj, zone_feats, time_feats) -> int:
        """Count number of confluence factors present."""
        count = 0
        if zone_feats.bos_detected:
            count += 1
        if zone_feats.choch_detected:
            count += 1
        if zone_feats.fvg_present:
            count += 1
        if zone_feats.liquidity_sweep:
            count += 1
        if time_feats.is_killzone:
            count += 1
        if htf_proj.htf_open_bias != "NEUTRAL":
            count += 1
        return count

    @staticmethod
    def _parse_timestamp(time_str: str) -> datetime:
        """Parse ISO 8601 timestamp string to UTC-aware datetime."""
        if not time_str:
            return datetime.now(tz=timezone.utc)
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(tz=timezone.utc)
