"""
Liquidity Engine - Pure-Python analytical package for ICT/TTrades methodology.

This package encodes the complete ICT/TTrades multi-timeframe Price Action methodology 
into a deterministic, stateless computation pipeline.

Entry point: LiquidityMappingEngine.analyze()
Output: LiquidityMap containing all analytical results

Usage:
    from liquidity_engine import LiquidityMappingEngine, LiquidityMap
    
    engine = LiquidityMappingEngine()
    liquidity_map = engine.analyze(candles_by_tf, instrument, timestamp)
"""
from __future__ import annotations

# Export the main classes
from liquidity_engine.models import (
    LiquidityMap, CISDCascadeStatus, SetupGradeDetail, SetupGrade
)

# Stub for LiquidityMappingEngine - will be implemented in engine.py
class LiquidityMappingEngine:
    """Main orchestrator class for liquidity analysis."""
    
    def analyze(self, candles_by_tf, instrument: str, timestamp):
        """Placeholder - will be implemented in task 147+."""
        return LiquidityMap(
            analyzed_at=timestamp,
            instrument=instrument,
            htf_bias={},
            liquidity_levels=[],
            pd_arrays=[],
            crt_phases={},
            cisd_cascade=CISDCascadeStatus(cascade_valid=False, cascade_chain=[]),
            draw_on_liquidity=None,
            sweep_detected=False,
            ote_zone=None,
            unicorn=None,
            setup_grade=SetupGradeDetail(
                grade=SetupGrade.NO_TRADE,
                conditions_met=0,
                htf_bias_confirmed=False,
                draw_on_liquidity_identified=False,
                liquidity_sweep_confirmed=False,
                displacement_present=False,
                cisd_confirmed=False,
                entry_pd_array_present=False,
                stop_placement_valid=False,
                time_window_aligned=False,
                grade_reason="No conditions met"
            ),
            swing_structure={},
            fractal_model=None
        )

__all__ = ["LiquidityMappingEngine", "LiquidityMap"]