"""
Liquidity Engine Data Models

All Pydantic v2 models for the complete ICT/TTrades methodology.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


# ===== ENUMS =====

class Timeframe(str, Enum):
    """Supported candle timeframes."""
    M1 = "M1"
    M3 = "M3"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H3 = "H3"
    H4 = "H4"
    H6 = "H6"
    H8 = "H8"
    H12 = "H12"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


class BiasDirection(str, Enum):
    """Directional bias states."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class PDArrayType(str, Enum):
    """Price Delivery Array types."""
    FVG = "FVG"                    # Fair Value Gap
    IFVG = "IFVG"                  # Inverse FVG (filled FVG, now opposing)
    OB = "OB"                      # Order Block
    BREAKER = "BREAKER"            # Breaker Block (violated OB, flipped polarity)
    BPR = "BPR"                    # Balanced Price Range (overlapping FVGs)
    CISD_LEVEL = "CISD_LEVEL"      # Open of first candle in violated delivery sequence


class LiquidityType(str, Enum):
    """Liquidity pool types."""
    BSL = "BSL"   # Buy-Side Liquidity (resting above highs — stops from shorts)
    SSL = "SSL"   # Sell-Side Liquidity (resting below lows — stops from longs)


class LiquiditySource(str, Enum):
    """Sources of liquidity levels."""
    PWH = "PWH"                    # Previous Week High
    PWL = "PWL"                    # Previous Week Low
    PDH = "PDH"                    # Previous Day High
    PDL = "PDL"                    # Previous Day Low
    PMH = "PMH"                    # Previous Month High
    PML = "PML"                    # Previous Month Low
    EQH = "EQH"                    # Equal Highs
    EQL = "EQL"                    # Equal Lows
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"
    TRENDLINE = "TRENDLINE"


class CRTPhase(str, Enum):
    """Candle Range Theory phases."""
    C1_ACCUMULATION = "C1_ACCUMULATION"
    C2_MANIPULATION = "C2_MANIPULATION"
    C3_DISTRIBUTION = "C3_DISTRIBUTION"
    C4_CONTINUATION = "C4_CONTINUATION"
    UNKNOWN = "UNKNOWN"


class PricePhase(str, Enum):
    """Price delivery phases."""
    EXPANSION = "EXPANSION"
    RETRACEMENT = "RETRACEMENT"
    CONSOLIDATION = "CONSOLIDATION"
    MANIPULATION = "MANIPULATION"


class SetupGrade(str, Enum):
    """Setup quality grades."""
    A_PLUS = "A+"
    A = "A"
    B = "B"
    NO_TRADE = "NO_TRADE"


class KillzoneWindow(str, Enum):
    """High-probability trading session windows."""
    LONDON = "LONDON"      # 02:00–05:00 EST
    NY_AM = "NY_AM"        # 07:00–10:00 EST
    NY_PM = "NY_PM"        # 13:30–16:00 EST
    NONE = "NONE"


class SwingTier(str, Enum):
    """Swing structure hierarchy tiers."""
    SHORT_TERM = "SHORT_TERM"              # STH / STL
    INTERMEDIATE_TERM = "INTERMEDIATE_TERM" # ITH / ITL
    LONG_TERM = "LONG_TERM"                # LTH / LTL


class StructureEventType(str, Enum):
    """Market structure events."""
    BOS = "BOS"       # Break of Structure — continuation
    CHOCH = "CHOCH"   # Change of Character — first sign of reversal


class CandleType(str, Enum):
    """Candle type classifications based on wick-to-range ratio."""
    EXPANSION = "EXPANSION"
    REVERSAL = "REVERSAL"
    REVERSAL_EXPANSION = "REVERSAL_EXPANSION"


class ClosureType(str, Enum):
    """Fractal model closure types."""
    CONTINUATION = "CONTINUATION"
    REVERSAL = "REVERSAL"


# ===== CORE MODELS =====

class Candle(BaseModel):
    """Single OHLCV candle. Immutable after construction."""
    model_config = ConfigDict(frozen=True)
    
    timestamp: datetime          # UTC, candle open time
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None
    timeframe: Timeframe
    instrument: str

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        """High must be >= open, low, and close.

        A cross-field check, so it must run after all fields are populated —
        a `field_validator` on `high` can only see fields declared earlier in
        the class body via `info.data`, which silently drops checks against
        `low`/`close` (declared after `high`).
        """
        if self.high < self.open:
            raise ValueError(f"high ({self.high}) must be >= open ({self.open})")
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        if self.high < self.close:
            raise ValueError(f"high ({self.high}) must be >= close ({self.close})")
        return self

    @property
    def is_bullish(self) -> bool:
        """True if close > open."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """True if close < open."""
        return self.close < self.open

    @property
    def body_size(self) -> float:
        """Absolute difference between close and open."""
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        """High minus low."""
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        """High minus the maximum of open and close."""
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        """Minimum of open and close minus low."""
        return min(self.open, self.close) - self.low


class HTFBias(BaseModel):
    """HTF directional bias for a single timeframe."""
    timeframe: Timeframe
    direction: BiasDirection
    reference_open: float        # The candle open used as the bias anchor
    reference_open_time: datetime
    current_price: float
    distance_from_open: float    # current_price - reference_open (signed)
    distance_pct: float          # distance as % of reference_open
    is_deep_premium: bool        # price far above open in bearish context
    is_deep_discount: bool       # price far below open in bullish context
    # Deep = price beyond midnight/08:30 reference in the opposing direction
    midnight_reference: Optional[float] = None   # 00:00 EST price
    news_reference: Optional[float] = None       # 08:30 EST price


class LiquidityLevel(BaseModel):
    """An identified external liquidity pool."""
    level_id: str                # UUID
    liquidity_type: LiquidityType   # BSL or SSL
    source: LiquiditySource
    price: float                 # exact price of the level
    timeframe: Timeframe         # timeframe on which it was identified
    formed_at: datetime          # when the level was created
    strength_score: float        # 0.0–1.0; higher = more significant
    touch_count: int             # number of times price has tested this level
    swept: bool = False          # True once price has traded through it
    swept_at: Optional[datetime] = None
    # For equal highs/lows: the tolerance band
    band_high: Optional[float] = None
    band_low: Optional[float] = None

    @field_validator("touch_count")
    @classmethod
    def touch_count_nonnegative(cls, v: int) -> int:
        """Touch count must be non-negative."""
        if v < 0:
            raise ValueError("touch_count must be >= 0")
        return v

    @field_validator("formed_at")
    @classmethod
    def formed_at_must_be_aware(cls, v: datetime) -> datetime:
        """Ensure formed_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("formed_at must be timezone-aware")
        return v


class PDArray(BaseModel):
    """A Price Delivery Array (imbalance or institutional footprint)."""
    array_id: str                # UUID
    array_type: PDArrayType
    direction: BiasDirection     # BULLISH = acts as support; BEARISH = acts as resistance
    timeframe: Timeframe
    high: float                  # upper boundary of the array
    low: float                   # lower boundary of the array
    formed_at: datetime          # timestamp of the candle that created it
    is_filled: bool = False      # True once price has fully traded through it
    filled_at: Optional[datetime] = None
    strength_score: float        # 0.0–1.0
    # For OB: the specific candle that is the order block
    ob_candle_open: Optional[float] = None
    ob_candle_close: Optional[float] = None
    # For Breaker: reference to the original OB it was derived from
    source_ob_id: Optional[str] = None
    # For Breaker: True once a same-tier BOS/CHoCH confirms the sweep-then-structural-break
    # sequence on the opposing side of the source OB (Requirement 4.15). Additive — never
    # gates BREAKER classification itself, only adds a confirmation signal.
    structure_confirmed: bool = False
    # For BPR: references to the two FVGs that form it
    bpr_bullish_fvg_id: Optional[str] = None
    bpr_bearish_fvg_id: Optional[str] = None
    # For CISD level: the open of the first candle in the violated sequence
    cisd_sequence_open: Optional[float] = None

    @model_validator(mode="after")
    def validate_high_gt_low(self) -> "PDArray":
        """High must be strictly greater than low (cross-field, see Candle.validate_ohlc)."""
        if self.high <= self.low:
            raise ValueError(f"high ({self.high}) must be > low ({self.low})")
        return self


class SwingPoint(BaseModel):
    """A single swing high or swing low at a given tier."""
    swing_id: str                  # UUID
    tier: SwingTier
    is_high: bool                  # True = swing high, False = swing low
    price: float
    formed_at: datetime
    broken: bool = False
    broken_at: Optional[datetime] = None
    # Present for INTERMEDIATE_TERM/LONG_TERM swings that were promoted from lower tiers
    derived_from_swing_id: Optional[str] = None

    @field_validator("formed_at")
    @classmethod
    def formed_at_must_be_aware(cls, v: datetime) -> datetime:
        """Ensure formed_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("formed_at must be timezone-aware")
        return v


class StructureEvent(BaseModel):
    """A market structure event (BOS/CHoCH)."""
    event_type: StructureEventType
    tier: SwingTier
    timeframe: Timeframe
    direction: BiasDirection
    broken_swing_id: str         # UUID of the swing that was broken
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def confirmed_at_must_be_aware(cls, v: datetime) -> datetime:
        """Ensure confirmed_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return v


class SwingStructureResult(BaseModel):
    """Complete swing structure analysis for a timeframe."""
    # Six lists for the three-tier hierarchy
    short_term_highs: List[SwingPoint] = []
    short_term_lows: List[SwingPoint] = []
    intermediate_term_highs: List[SwingPoint] = []
    intermediate_term_lows: List[SwingPoint] = []
    long_term_highs: List[SwingPoint] = []
    long_term_lows: List[SwingPoint] = []
    # Structure events
    events: List[StructureEvent] = []
    latest_event: Optional[StructureEvent] = None


class CRTPhaseResult(BaseModel):
    """Candle Range Theory phase classification result."""
    phase: CRTPhase
    confidence: float            # 0.0–1.0
    c1_range_high: Optional[float] = None
    c1_range_low: Optional[float] = None
    c2_within_c1: bool = False
    confirmation_tf_cisd: bool = False


class CISDResult(BaseModel):
    """Change in State of Delivery detection result."""
    direction: BiasDirection
    level: float                 # open of first candle in sequence
    sequence_start_time: datetime
    violation_candle_time: datetime
    confirmed: bool
    has_swing_prerequisite: bool


class CISDCascadeStatus(BaseModel):
    """CISD cascade validation status."""
    cascade_valid: bool
    cascade_chain: List[CISDResult] = []


class OTEZone(BaseModel):
    """Optimal Trade Entry Fibonacci zone."""
    fib_62: float
    fib_705: float
    fib_79: float
    ote_low: float
    ote_high: float
    golden_level: float
    price_in_ote: bool
    displacement_leg_high: float
    displacement_leg_low: float


class SDProjection(BaseModel):
    """Standard Deviation projection targets beyond a displacement leg.

    Anchored on the same leg/direction convention as OTEZone (see
    liquidity_engine/ote/calculator.py's module docstring): anchor_0 is the
    "0%" fib point (swing_high for bullish, swing_low for bearish — where
    retracement measurement starts), anchor_1 is the "100%" point (the
    opposite extreme). Targets project *beyond* anchor_0, in the direction
    away from anchor_1 — i.e. the continuation direction once the leg's own
    retracement (OTE) completes. ``targets`` keys are the SD multiples
    TTrades charts as 1/-1, 2/-2, 2.5/-2.5, 4/-4, 4.5/-4.5 — stored here as
    positive multiples since the sign in TTrades' own UI only encodes "past
    the 0 anchor," not a separate direction.
    """
    anchor_0: float
    anchor_1: float
    targets: Dict[float, float]


class UnicornPattern(BaseModel):
    """UNICORN pattern - overlapping Breaker Block and FVG."""
    breaker_array_id: str
    fvg_array_id: str
    overlap_high: float
    overlap_low: float
    direction: BiasDirection
    formed_at: datetime
    strength_score: float


class SetupGradeDetail(BaseModel):
    """Complete setup grading breakdown."""
    grade: SetupGrade
    conditions_met: int          # Count of True conditions
    # The 8 boolean conditions
    htf_bias_confirmed: bool
    draw_on_liquidity_identified: bool
    liquidity_sweep_confirmed: bool
    displacement_present: bool
    cisd_confirmed: bool
    entry_pd_array_present: bool
    stop_placement_valid: bool
    time_window_aligned: bool
    # Additional fields
    grade_reason: str
    suggested_entry: Optional[float] = None
    suggested_stop: Optional[float] = None
    # The entry array's own range/direction — the local LTF leg price
    # retraces into its discount/premium *within*, as distinct from the
    # broader HTF displacement leg OTEZone anchors on. Used to project SD
    # targets at a scale proportionate to this entry, not the whole swing.
    entry_array_high: Optional[float] = None
    entry_array_low: Optional[float] = None
    entry_array_direction: Optional[BiasDirection] = None


class FractalCandleStep(BaseModel):
    """Single step in the Fractal Model sequence."""
    step_number: int
    candle: Candle
    closure_type: Optional[ClosureType] = None  # None for step 1


class FractalModelResult(BaseModel):
    """Fractal Model tracking result."""
    key_level: float
    steps: List[FractalCandleStep]
    range_high: float
    range_low: float
    equilibrium: float
    price_above_equilibrium: bool


class LiquidityMap(BaseModel):
    """Complete liquidity analysis output."""
    analyzed_at: datetime
    instrument: str
    htf_bias: Dict[str, HTFBias]                        # Keyed by Timeframe.value
    liquidity_levels: List[LiquidityLevel]
    pd_arrays: List[PDArray]
    crt_phases: Dict[str, CRTPhaseResult]               # Keyed by Timeframe.value
    cisd_cascade: Optional[CISDCascadeStatus]
    draw_on_liquidity: Optional[LiquidityLevel]
    sweep_detected: bool
    ote_zone: Optional[OTEZone]
    unicorn: Optional[UnicornPattern]
    setup_grade: Optional[SetupGradeDetail]
    swing_structure: Dict[str, SwingStructureResult] = {}    # Keyed by Timeframe.value
    fractal_model: Optional[FractalModelResult] = None
    sd_projection: Optional[SDProjection] = None

    def get_bias(self, timeframe: Timeframe) -> Optional[HTFBias]:
        """Get HTF bias for a specific timeframe."""
        return self.htf_bias.get(timeframe.value)

    def get_arrays_by_type(self, array_type: PDArrayType) -> List[PDArray]:
        """Get all PD arrays of a specific type."""
        return [array for array in self.pd_arrays if array.array_type == array_type]

    def get_arrays_in_range(self, price_low: float, price_high: float) -> List[PDArray]:
        """Get unfilled PD arrays within a price range."""
        return [
            array for array in self.pd_arrays
            if not array.is_filled
            and array.low <= price_high
            and array.high >= price_low
        ]

    def to_agent_context(self) -> str:
        """Render this LiquidityMap as an LLM-readable narrative.

        Answers the three questions the agent's reasoning is built around, in
        order: where has price come from, where is it now, where is it likely
        to go. Sections with nothing to report (no structure event yet, no
        fractal model, no draw target) are omitted rather than left blank.
        """
        lines: List[str] = [f"# Liquidity Analysis: {self.instrument}", ""]

        lines.append("## Where has price come from?")
        for tf_value, bias in self.htf_bias.items():
            lines.append(f"- {tf_value} bias: {bias.direction.value} (open {bias.reference_open})")
        latest_event = self._latest_structure_event()
        if latest_event is not None:
            lines.append(
                f"- Most recent structure event: {latest_event.event_type.value} "
                f"({latest_event.direction.value}, {latest_event.tier.value}, "
                f"{latest_event.timeframe.value})"
            )
        lines.append("")

        lines.append("## Where is it now?")
        if self.crt_phases:
            for tf_value, phase in self.crt_phases.items():
                lines.append(f"- {tf_value} CRT phase: {phase.phase.value}")
        if self.fractal_model is not None:
            stance = "above" if self.fractal_model.price_above_equilibrium else "at or below"
            lines.append(f"- Price is {stance} the Fractal Model equilibrium ({self.fractal_model.equilibrium})")
        lines.append("")

        lines.append("## Where is it likely to go?")
        if self.draw_on_liquidity is not None:
            lines.append(
                f"- Draw on liquidity: {self.draw_on_liquidity.source.value} "
                f"at {self.draw_on_liquidity.price} ({self.draw_on_liquidity.liquidity_type.value})"
            )
        if self.ote_zone is not None:
            lines.append(
                f"- OTE zone: {self.ote_zone.ote_low}-{self.ote_zone.ote_high} "
                f"(golden level {self.ote_zone.golden_level})"
            )
        if self.sd_projection is not None:
            targets_str = ", ".join(
                f"{level}={price:.5f}" for level, price in sorted(self.sd_projection.targets.items())
            )
            lines.append(f"- SD projection targets: {targets_str}")
        if self.setup_grade is not None:
            lines.append(
                f"- Setup grade: {self.setup_grade.grade.value} "
                f"({self.setup_grade.conditions_met}/8 conditions met)"
            )

        return "\n".join(lines)

    def _latest_structure_event(self) -> Optional["StructureEvent"]:
        events = [
            result.latest_event
            for result in self.swing_structure.values()
            if result.latest_event is not None
        ]
        if not events:
            return None
        return max(events, key=lambda e: e.confirmed_at)