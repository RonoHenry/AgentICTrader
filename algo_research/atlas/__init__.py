"""The turn atlas (algo-research update 2026-10g): every swing point, what it delivered, and what was true when
it formed. The user's framework, reverse-engineered on the exploration slice.

    python -m algo_research atlas

- ``arrays``: FVGs and order blocks as the user reads them (Requirement 23).
- ``swings``: every three-candle and engulfing swing, scored against its objectives (Requirement 24).
- ``context``: what was true when each swing formed: arrays, liquidity, range, time, anatomy (Requirement 25).
- ``report``: base rates, every context value against them, and ``docs/research/TURN_ATLAS.md`` (Requirement 26).
"""
