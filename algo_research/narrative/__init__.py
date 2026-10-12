"""The market narrative: how finished candles formed (.kiro/specs/market-narrative).

trading-method.md keeps two records per candle: the read, written at the open,
and the narrative, written after the close. This package computes the
narrative. It is hindsight: the autopsy and research labels read it; nothing
that decides imports it (a test checks the imports).

    bars = apply_price_basis(bars, "EURUSD", cfg.price_basis)
    days = narrate(bars, Timeframe.M15, Timeframe.D1)
    phase = fill_phase(days.iloc[0], fill_bar_open)
"""
from algo_research.narrative.candles import CHILD, NARRATIVE_COLUMNS, PHASES, fill_phase, narrate
from algo_research.narrative.config import NarrativeConfig, PriceBasis, load_narrative_config
from algo_research.narrative.prices import apply_price_basis

__all__ = ["CHILD", "NARRATIVE_COLUMNS", "PHASES", "NarrativeConfig", "PriceBasis", "apply_price_basis",
           "fill_phase", "load_narrative_config", "narrate"]
