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
from liquidity_engine.engine import LiquidityMappingEngine
from liquidity_engine.models import LiquidityMap

__all__ = ["LiquidityMappingEngine", "LiquidityMap"]