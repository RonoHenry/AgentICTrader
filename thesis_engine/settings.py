"""Every rule and threshold the Thesis Engine uses (thesis-engine Requirement 1.4).

``V1`` holds the defaults put to the trader in design.md ("Decisions for the Trader"), frozen for H-AG. Changing any
value is a new version and a new registration, never an edit of V1.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from algomind_dis.settings import V2 as DIS_V2, Settings as DisSettings

__all__ = ["INDICES", "Settings", "V1", "V2"]

#: The indices' trading day opens at 18:00 New York; FX, gold and DXY at 17:00 (the trader's H4 clock, TE-D11).
INDICES = frozenset({"US100", "US500", "US30", "GER40", "UK100"})


@dataclass(frozen=True)
class Settings:
    version: str = "v1"
    #: The analyzers' settings the book reads: V2, the trader's order blocks and breakers (TE-D4).
    dis: DisSettings = DIS_V2
    #: The ladder (TE-D12): the level frames and the execution frame.
    level_frames: tuple = ("D1", "H4", "H1")
    e_frame: str = "M5"
    #: Decision 9's default: the trader's three-candle swing on the execution frame (one candle each side); the
    #: level frames' swings are the analyzers' (lookback 2), unchanged.
    e_swing_lookback: int = 1
    #: The window (TE-D6): New York hours [start, end), Monday to Friday: Q2-Q3.
    window: tuple = (0, 12)
    #: The hand (TE-D7): the sweep's pool within this many ADR under a bullish level, and the CISD within this many
    #: E candles of the sweep.
    pool_band_adr: float = 0.1
    hand_candles: int = 12
    #: A level is at most this many ADR tall (context-engine Requirement 34).
    level_max_adr: float = 1.0
    #: Risk (TE-D8).
    min_stop_spreads: float = 10.0
    min_rr: float = 2.0
    per_day: int = 1
    per_thesis: int = 2
    #: Data with no bar for longer than this inside a trading day is stale (TE-D17).
    stale_minutes: int = 15
    #: ADR: the mean D1 range over this many closed days.
    adr_days: int = 20
    #: The completion rule for the research sources (Requirement 4.4).
    completion_min_adr: float = 0.5
    completion_max_adr: float = 5.0
    #: The hand's pools: "M5_SWINGS" (V1: the E frame's swings and the previous H1 extreme) or "TRADER" (V2: the
    #: previous D1, H4 and H1 extremes, the Asia range and untaken H1 swings; Requirement 15.2).
    hand_pools: str = "M5_SWINGS"
    #: The CISD candle's body, in E average ranges of the 20 candles before it (0: no test; V2: 1.5).
    displacement_body: float = 0.0
    #: The entry: "MARKET" at the CISD close (V1) or "LIMIT_MT" at the CISD run's bodies' midpoint (V2), expiring
    #: at the window's end or ``limit_minutes`` after it is placed, whichever is later.
    entry: str = "MARKET"
    limit_minutes: int = 60
    #: The stack gate: a level needs arrays of the side on this many level frames, or to be a D1 array (V2: 2).
    stack_min_frames: int = 1
    #: Levels of equal score and distance: "ID" (V1: by the array's content id) or "FRAME" (V2: the higher frame,
    #: then the tighter zone, then the latest formed; the same choice in a mirrored market).
    level_tiebreak: str = "ID"

    def day_open_hour(self, market: str) -> int:
        return 18 if market.upper() in INDICES else 17


V1 = Settings()
#: V2 (Requirement 15, registered as H-AH before it ran): the trader's pools, a displacement, a limit at the run's MT
#: and the stack as a gate. Everything else is V1.
V2 = replace(V1, version="v2", hand_pools="TRADER", displacement_body=1.5, entry="LIMIT_MT", stack_min_frames=2,
             level_tiebreak="FRAME")
