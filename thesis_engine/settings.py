"""Every rule and threshold the Thesis Engine uses (thesis-engine Requirement 1.4).

``V1`` holds the defaults put to the trader in design.md ("Decisions for the Trader"), frozen for H-AG. Changing any
value is a new version and a new registration, never an edit of V1.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from algomind_dis.settings import V2 as DIS_V2, Settings as DisSettings

__all__ = ["INDICES", "MINUTES", "Settings", "V1", "V2", "V3", "V4"]

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
    #: The entry: "MARKET" at the CISD close (V1), "LIMIT_MT" at the CISD run's bodies' midpoint (V2), expiring
    #: at the window's end or ``limit_minutes`` after it is placed, whichever is later, or "NEAR_MT" (V3): at market
    #: when the close is near that midpoint, a limit at it otherwise.
    entry: str = "MARKET"
    limit_minutes: int = 60
    #: The stack gate: a level needs arrays of the side on this many level frames, or to be a D1 array (V2: 2).
    stack_min_frames: int = 1
    #: Levels of equal score and distance: "ID" (V1: by the array's content id) or "FRAME" (V2: the higher frame,
    #: then the tighter zone, then the latest formed; the same choice in a mirrored market).
    level_tiebreak: str = "ID"
    #: The hand's frame: "" (V1, V2: the E frame) or "POOL" (V3: the child of the swept pool's frame, the largest of
    #: ``exec_frames`` no longer than a tenth of it; Requirement 17.4).
    exec_child: str = ""
    exec_frames: tuple = ()
    #: Frames whose untaken swings are pools too (V3: M30 and M15).
    swing_pools: tuple = ()
    #: The run into the sweep may end this many child candles before the sweep's (V3: 1).
    run_slack: int = 0
    #: "NEAR_MT" entries (V3) go at market when the CISD close is within this many child average ranges of the run's
    #: MT, and as a limit at the MT otherwise.
    near_mt: float = 0.5
    #: The setup frame of each pool's frame, as pairs (V4); empty: the largest execution frame no longer than a tenth
    #: of the pool's frame (V3).
    child_map: tuple = ()
    #: "REFINED" entries (V4): each setup frame's refining frame, whose CISD inside the setup's order block enters.
    refine: tuple = ()

    def day_open_hour(self, market: str) -> int:
        return 18 if market.upper() in INDICES else 17

    def child(self, pool_tf: str) -> str:
        """The execution frame a pool of ``pool_tf`` is confirmed on (V3, V4)."""
        if self.child_map:
            return dict(self.child_map)[pool_tf]
        cap = MINUTES[pool_tf] / 10
        return max((tf for tf in self.exec_frames if MINUTES[tf] <= cap), key=lambda tf: MINUTES[tf])


#: Each frame's length in minutes; the Asia range (from the trading day's open to 00:00 New York) counts as six hours.
MINUTES = {"M1": 1, "M3": 3, "M5": 5, "M10": 10, "M15": 15, "M20": 20, "M30": 30, "H1": 60, "H4": 240, "ASIA": 360,
           "D1": 1440}

V1 = Settings()
#: V2 (Requirement 15, registered as H-AH before it ran): the trader's pools, a displacement, a limit at the run's MT
#: and the stack as a gate. Everything else is V1.
V2 = replace(V1, version="v2", hand_pools="TRADER", displacement_body=1.5, entry="LIMIT_MT", stack_min_frames=2,
             level_tiebreak="FRAME")
#: V3 (Requirement 17, registered as H-AI before it ran): the machine steps on M1, and each hand runs on its pool's
#: child frame, from M30 down to M1; at market near the run's MT, a limit at it when price has run. Everything else
#: is V2.
V3 = replace(V2, version="v3", e_frame="M1", exec_child="POOL",
             exec_frames=("M30", "M20", "M15", "M10", "M5", "M3", "M1"), swing_pools=("M30", "M15"), run_slack=1,
             entry="NEAR_MT", near_mt=0.5)
#: V4 (Requirement 19, registered as H-AJ before it ran): setups only on M30 (the previous day, the Asia range, the
#: previous H4) and M15 (the previous H1, H1 swings); the entry at market on an M3 or M1 CISD once price is back in
#: the setup's order block, the stop at the setup's sweep. Everything else is V3.
V4 = replace(V3, version="v4", exec_frames=("M30", "M15"),
             child_map=(("D1", "M30"), ("ASIA", "M30"), ("H4", "M30"), ("H1", "M15")), swing_pools=(),
             entry="REFINED", refine=(("M30", "M3"), ("M15", "M1")))
