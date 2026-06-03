# Design Document: Liquidity Engine

## Overview

The Liquidity Engine is a pure-Python analytical package that encodes the complete ICT/TTrades multi-timeframe trading methodology into a deterministic, stateless computation pipeline. It consumes multi-timeframe OHLCV candle data and produces a `LiquidityMap`  a structured object containing every analytical output the methodology requires: HTF bias per timeframe, all identified liquidity levels (BSL/SSL), all PD arrays (FVG, OB, Breaker, IFVG, BPR, CISD), CRT phase classification, CISD cascade status, draw-on-liquidity target, sweep detection, UNICORN pattern detection, OTE Fibonacci zone, and a final setup grade (A+/A/B/NO_TRADE).

The engine is designed to be called once per candle close from `agent/nodes/observe_node.py`. Its output is stored on `AgentState.liquidity_map` and injected into the LLM reasoning prompt via `LiquidityMap.to_agent_context()`. It replaces `backend/trader/agents/power_of_3.py`, `backend/trader/analysis/patterns.py`, and the stub `backend/trader/agents/pd_array/` directory. A `services/liquidity/` microservice will wrap it for HTTP/Kafka access post-v1.

This spec is **parked for post-v1 implementation** (after tasks 143 ship). It is written to be complete enough for any developer to implement without further clarification.

---

## Architecture

```mermaid
graph TD
    A[Multi-TF OHLCV Input] --> B[LiquidityMappingEngine]
    B --> C[HTFBiasClassifier]
    B --> D[LiquidityLevelDetector]
    B --> E[PDArrayDetector]
    B --> F[IPDAClassifier]
    B --> G[OTECalculator]
    B --> H[UnicornDetector]
    B --> I[SetupGrader]
    C --> J[LiquidityMap]
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K[AgentState.liquidity_map]
    J --> L[to_agent_context()  LLM prompt]
```

```mermaid
graph LR
    subgraph liquidity_engine/
        M[models.py] --> N[engine.py]
        O[detectors/external.py] --> N
        P[detectors/internal.py] --> N
        Q[detectors/institutional.py] --> N
        R[ipda/classifier.py] --> N
        S[ipda/cisd.py] --> N
        T[ote/calculator.py] --> N
        U[unicorn/detector.py] --> N
        V[grader/setup_grader.py] --> N
        W[utils/time_utils.py] --> N
        X[utils/candle_utils.py] --> N
    end
    N --> Y[LiquidityMap]
```

### Package Layout

```
liquidity_engine/
 __init__.py                  # exports: LiquidityMappingEngine, LiquidityMap
 models.py                    # all Pydantic v2 data models
 engine.py                    # LiquidityMappingEngine (orchestrator)
 detectors/
    __init__.py
    external.py              # BSL/SSL, PWH/PWL/PDH/PDL, equal highs/lows
    internal.py              # FVG, IFVG, OB, Breaker, BPR, CISD level
    institutional.py        # session highs/lows, trendline liquidity
 ipda/
    __init__.py
    classifier.py            # CRT phase detection (C1/C2/C3/C4)
    cisd.py                  # CISD detection + cascade validation
 ote/
    __init__.py
    calculator.py            # Fibonacci OTE zone (0.620.79)
 unicorn/
    __init__.py
    detector.py              # Breaker + FVG overlap detection
 grader/
    __init__.py
    setup_grader.py          # A+/A/B/NO_TRADE scoring
 utils/
     __init__.py
     time_utils.py            # EST/UTC-4 conversions, killzone windows
     candle_utils.py          # swing point detection, candle helpers
```

---

## Sequence Diagrams

### Main Engine Call (per candle close)

```mermaid
sequenceDiagram
    participant ON as observe_node
    participant LE as LiquidityMappingEngine
    participant HB as HTFBiasClassifier
    participant LD as LiquidityLevelDetector
    participant PD as PDArrayDetector
    participant IP as IPDAClassifier
    participant OT as OTECalculator
    participant UN as UnicornDetector
    participant SG as SetupGrader
    participant LM as LiquidityMap

    ON->>LE: analyze(candles_by_tf, instrument, ts)
    LE->>HB: classify_bias(candles_by_tf)
    HB-->>LE: Dict[Timeframe, HTFBias]
    LE->>LD: detect_levels(candles_by_tf)
    LD-->>LE: List[LiquidityLevel]
    LE->>PD: detect_arrays(candles_by_tf)
    PD-->>LE: List[PDArray]
    LE->>IP: classify_crt(candles_by_tf)
    IP-->>LE: Dict[Timeframe, CRTPhase]
    LE->>IP: validate_cisd_cascade(candles_by_tf)
    IP-->>LE: CISDCascadeStatus
    LE->>OT: calculate_ote(displacement_leg)
    OT-->>LE: OTEZone
    LE->>UN: detect(pd_arrays)
    UN-->>LE: Optional[UnicornPattern]
    LE->>SG: grade(bias, levels, arrays, cisd, ote, unicorn, ts)
    SG-->>LE: SetupGrade
    LE-->>ON: LiquidityMap
```

### CISD Cascade Validation

```mermaid
sequenceDiagram
    participant IP as IPDAClassifier
    participant CS as CISDDetector
    participant TF as TimeframeHierarchy

    IP->>TF: get_confirmation_tf(trigger_tf)
    TF-->>IP: confirmation_tf
    IP->>CS: detect_cisd(candles[confirmation_tf])
    CS-->>IP: CISDResult(confirmed, direction, level)
    IP->>CS: validate_swing_point_prerequisite(candles[confirmation_tf])
    CS-->>IP: has_3_candle_swing
    IP-->>IP: cascade_valid = confirmed AND has_3_candle_swing
```

---

## Components and Interfaces

### LiquidityMappingEngine

**Purpose**: Top-level orchestrator. Accepts raw multi-timeframe candle data, runs all sub-detectors in dependency order, assembles and returns a `LiquidityMap`.

**Interface**:
```python
class LiquidityMappingEngine:
    def analyze(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        instrument: str,
        timestamp: datetime,
    ) -> LiquidityMap: ...

    def _classify_htf_bias(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> Dict[Timeframe, HTFBias]: ...

    def _detect_liquidity_levels(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> List[LiquidityLevel]: ...

    def _detect_pd_arrays(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> List[PDArray]: ...

    def _classify_crt_phases(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> Dict[Timeframe, CRTPhase]: ...

    def _validate_cisd_cascade(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> CISDCascadeStatus: ...

    def _find_draw_on_liquidity(
        self,
        bias: Dict[Timeframe, HTFBias],
        levels: List[LiquidityLevel],
    ) -> Optional[LiquidityLevel]: ...

    def _detect_sweep(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        draw: Optional[LiquidityLevel],
    ) -> bool: ...
```

**Responsibilities**:
- Validate that required timeframes are present in input
- Call sub-components in correct dependency order
- Assemble the final `LiquidityMap`
- Never mutate input candle data

### HTFBiasClassifier

**Purpose**: Determines BULLISH/BEARISH/NEUTRAL bias for each timeframe by comparing current price to that timeframe's candle open. Implements Layer 1 of the methodology.

**Interface**:
```python
class HTFBiasClassifier:
    def classify(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        current_price: float,
    ) -> Dict[Timeframe, HTFBias]: ...

    def _get_reference_open(
        self, tf: Timeframe, candles: List[Candle], timestamp: datetime
    ) -> float: ...
```

**Responsibilities**:
- For DAILY: use NY midnight (00:00 EST) open as primary reference; 18:00 EST open as secondary
- For WEEKLY: use Sunday 18:00 EST open
- For MONTHLY: use first candle open of the calendar month
- BULLISH = current price above open (hunt longs below open)
- BEARISH = current price below open (hunt shorts above open)
- NEUTRAL = price within 0.01% of open (instrument-relative tolerance)

### LiquidityLevelDetector (detectors/external.py + institutional.py)

**Purpose**: Identifies all external liquidity pools where stop orders rest. Implements Layer 5.

**Interface**:
```python
class LiquidityLevelDetector:
    def detect(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        timestamp: datetime,
    ) -> List[LiquidityLevel]: ...

    def _detect_previous_highs_lows(
        self, candles_by_tf: Dict[Timeframe, List[Candle]]
    ) -> List[LiquidityLevel]: ...

    def _detect_equal_highs_lows(
        self, candles: List[Candle], tolerance_pct: float = 0.001
    ) -> List[LiquidityLevel]: ...

    def _detect_session_highs_lows(
        self, candles: List[Candle], timestamp: datetime
    ) -> List[LiquidityLevel]: ...

    def _score_level(
        self, level: LiquidityLevel, candles: List[Candle]
    ) -> float: ...
```

**Responsibilities**:
- Detect PWH/PWL (previous week high/low) from weekly candles
- Detect PDH/PDL (previous day high/low) from daily candles
- Detect PMH/PML (previous month high/low) from monthly candles
- Detect equal highs/lows: two or more swing points within `tolerance_pct` of each other
- Detect session highs/lows (London, NY AM, NY PM) from intraday candles
- Score each level by: number of touches, timeframe significance, recency

### PDArrayDetector (detectors/internal.py)

**Purpose**: Detects all Price Delivery Arrays. Implements Layer 6.

**Interface**:
```python
class PDArrayDetector:
    def detect(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
    ) -> List[PDArray]: ...

    def _detect_fvg(
        self, candles: List[Candle], tf: Timeframe
    ) -> List[PDArray]: ...

    def _detect_order_blocks(
        self, candles: List[Candle], tf: Timeframe
    ) -> List[PDArray]: ...

    def _detect_breaker_blocks(
        self, candles: List[Candle], ob_list: List[PDArray]
    ) -> List[PDArray]: ...

    def _detect_ifvg(
        self, candles: List[Candle], fvg_list: List[PDArray]
    ) -> List[PDArray]: ...

    def _detect_bpr(
        self, fvg_list: List[PDArray]
    ) -> List[PDArray]: ...

    def _detect_cisd_levels(
        self, candles: List[Candle], tf: Timeframe
    ) -> List[PDArray]: ...
```

**Responsibilities**:
- FVG: 3-candle imbalance  gap between `candles[i-2].low` and `candles[i].high` (bullish) or `candles[i-2].high` and `candles[i].low` (bearish)
- OB: last up-close candle before bearish expansion (bearish OB); last down-close candle before bullish expansion (bullish OB)
- Breaker: violated OB that has flipped polarity  track OBs that price has traded through and tag as breaker
- IFVG: previously filled FVG (price has traded through it)  now acts as opposing array
- BPR: overlapping bullish FVG and bearish FVG at the same price level
- CISD level: the open price of the first candle in the delivery sequence that was violated

### IPDAClassifier (ipda/classifier.py + ipda/cisd.py)

**Purpose**: Classifies CRT phase (C1/C2/C3/C4) per timeframe and validates the CISD cascade. Implements Layer 3.

**Interface**:
```python
class IPDAClassifier:
    CISD_CASCADE: Dict[Timeframe, Timeframe] = {
        Timeframe.MONTHLY: Timeframe.DAILY,
        Timeframe.WEEKLY: Timeframe.H4,
        Timeframe.DAILY: Timeframe.H1,
        Timeframe.H4: Timeframe.M15,
        Timeframe.M30: Timeframe.M3,
        Timeframe.M15: Timeframe.M1,
    }

    def classify_crt_phase(
        self, candles: List[Candle], tf: Timeframe
    ) -> CRTPhase: ...

    def validate_cisd_cascade(
        self,
        candles_by_tf: Dict[Timeframe, List[Candle]],
        trigger_tf: Timeframe,
    ) -> CISDCascadeStatus: ...

class CISDDetector:
    def detect(
        self, candles: List[Candle]
    ) -> Optional[CISDResult]: ...

    def _has_swing_point_prerequisite(
        self, candles: List[Candle]
    ) -> bool: ...
```

**Responsibilities**:
- C1 (Accumulation): range-building candles, ATR-relative tight range
- C2 (Manipulation): candle that closes within C1's range AND lower-TF CISD is confirmed
- C3 (Distribution/Expansion): strong directional candle away from C2
- C4 (Continuation): follow-through in C3 direction
- Bearish CISD: series of up-close candles  close BELOW open of first candle in sequence
- Bullish CISD: series of down-close candles  close ABOVE open of first candle in sequence
- Swing point prerequisite: price cannot reverse without a 3-candle swing point first

### OTECalculator (ote/calculator.py)

**Purpose**: Calculates the Optimal Trade Entry Fibonacci zone from the last displacement leg. Implements Layer 7 (OTE model).

**Interface**:
```python
class OTECalculator:
    FIBONACCI_LEVELS: List[float] = [0.0, 0.5, 0.62, 0.705, 0.79, 1.0]
    OTE_LOW: float = 0.62
    OTE_HIGH: float = 0.79
    GOLDEN_LEVEL: float = 0.705

    def calculate(
        self,
        swing_high: float,
        swing_low: float,
        direction: BiasDirection,
    ) -> OTEZone: ...

    def find_displacement_leg(
        self,
        candles: List[Candle],
        direction: BiasDirection,
    ) -> Optional[tuple[float, float]]: ...

    def price_in_ote(
        self, price: float, ote_zone: OTEZone
    ) -> bool: ...
```

**Responsibilities**:
- Anchor from swing HIGH to swing LOW for bullish setups (retracement into discount)
- Anchor from swing LOW to swing HIGH for bearish setups (retracement into premium)
- OTE zone = 0.62 to 0.79 retracement of the displacement leg
- Golden level = 0.705 (highest probability single entry price)
- Displacement leg = the most recent impulsive move that created a FVG

### UnicornDetector (unicorn/detector.py)

**Purpose**: Detects the UNICORN pattern  a Breaker Block and FVG overlapping at the same price level. Implements Layer 7 (UNICORN model).

**Interface**:
```python
class UnicornDetector:
    def detect(
        self,
        pd_arrays: List[PDArray],
        overlap_tolerance_pct: float = 0.001,
    ) -> Optional[UnicornPattern]: ...

    def _arrays_overlap(
        self,
        a: PDArray,
        b: PDArray,
        tolerance_pct: float,
    ) -> bool: ...
```

**Responsibilities**:
- Bullish UNICORN: Bullish Breaker Block + Bullish FVG with overlapping price ranges
- Bearish UNICORN: Bearish Breaker Block + Bearish FVG with overlapping price ranges
- Overlap = the intersection of the two arrays' price ranges
- Return the most recently formed UNICORN if multiple exist

### SetupGrader (grader/setup_grader.py)

**Purpose**: Evaluates all 8 A+ conditions and assigns a setup grade. Implements Layer 8.

**Interface**:
```python
class SetupGrader:
    def grade(
        self,
        liquidity_map: "LiquidityMap",
        timestamp: datetime,
    ) -> SetupGrade: ...

    def _check_htf_bias(self, lm: "LiquidityMap") -> bool: ...
    def _check_draw_on_liquidity(self, lm: "LiquidityMap") -> bool: ...
    def _check_liquidity_sweep(self, lm: "LiquidityMap") -> bool: ...
    def _check_displacement(self, lm: "LiquidityMap") -> bool: ...
    def _check_cisd(self, lm: "LiquidityMap") -> bool: ...
    def _check_entry_pd_array(self, lm: "LiquidityMap") -> bool: ...
    def _check_stop_placement(self, lm: "LiquidityMap") -> bool: ...
    def _check_time_window(self, lm: "LiquidityMap", ts: datetime) -> bool: ...
```

**Responsibilities**:
- A+ requires ALL 8 conditions true
- Grade A: 7/8 conditions  missing killzone alignment OR UNICORN (has OTE or single PD array)
- Grade B: sweep + CISD confirmed but entry PD array is weaker (FVG only, no breaker)
- NO_TRADE: fewer than 6 conditions met, or HTF bias missing, or no draw on liquidity

---

## Data Models

All models use Pydantic v2. All price values are `float`. All timestamps are `datetime` (timezone-aware, UTC stored, EST displayed).

### Enums

```python
from enum import Enum

class Timeframe(str, Enum):
    M1  = "M1"
    M3  = "M3"
    M5  = "M5"
    M15 = "M15"
    M30 = "M30"
    H1  = "H1"
    H4  = "H4"
    D1  = "D1"
    W1  = "W1"
    MN1 = "MN1"

class BiasDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class PDArrayType(str, Enum):
    FVG          = "FVG"           # Fair Value Gap
    IFVG         = "IFVG"          # Inverse FVG (filled FVG, now opposing)
    OB           = "OB"            # Order Block
    BREAKER      = "BREAKER"       # Breaker Block (violated OB, flipped polarity)
    BPR          = "BPR"           # Balanced Price Range (overlapping FVGs)
    CISD_LEVEL   = "CISD_LEVEL"    # Open of first candle in violated delivery sequence

class LiquidityType(str, Enum):
    BSL = "BSL"   # Buy-Side Liquidity (resting above highs  stops from shorts)
    SSL = "SSL"   # Sell-Side Liquidity (resting below lows  stops from longs)

class LiquiditySource(str, Enum):
    PWH    = "PWH"    # Previous Week High
    PWL    = "PWL"    # Previous Week Low
    PDH    = "PDH"    # Previous Day High
    PDL    = "PDL"    # Previous Day Low
    PMH    = "PMH"    # Previous Month High
    PML    = "PML"    # Previous Month Low
    EQH    = "EQH"    # Equal Highs
    EQL    = "EQL"    # Equal Lows
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW  = "SESSION_LOW"
    TRENDLINE    = "TRENDLINE"

class CRTPhase(str, Enum):
    C1_ACCUMULATION  = "C1_ACCUMULATION"
    C2_MANIPULATION  = "C2_MANIPULATION"
    C3_DISTRIBUTION  = "C3_DISTRIBUTION"
    C4_CONTINUATION  = "C4_CONTINUATION"
    UNKNOWN          = "UNKNOWN"

class PricePhase(str, Enum):
    EXPANSION     = "EXPANSION"
    RETRACEMENT   = "RETRACEMENT"
    CONSOLIDATION = "CONSOLIDATION"
    MANIPULATION  = "MANIPULATION"

class SetupGrade(str, Enum):
    A_PLUS   = "A+"
    A        = "A"
    B        = "B"
    NO_TRADE = "NO_TRADE"

class KillzoneWindow(str, Enum):
    LONDON    = "LONDON"      # 02:0005:00 EST
    NY_AM     = "NY_AM"       # 07:0010:00 EST
    NY_PM     = "NY_PM"       # 13:3016:00 EST
    NONE      = "NONE"
```

### Core Candle Model

```python
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional

class Candle(BaseModel):
    """Single OHLCV candle. Immutable after construction."""
    timestamp: datetime          # UTC, candle open time
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None
    timeframe: Timeframe
    instrument: str

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: float, info) -> float:
        if "low" in info.data and v < info.data["low"]:
            raise ValueError(f"high ({v}) must be >= low ({info.data['low']})")
        return v

    @field_validator("high")
    @classmethod
    def high_gte_open_close(cls, v: float, info) -> float:
        for field in ("open", "close"):
            if field in info.data and v < info.data[field]:
                raise ValueError(f"high ({v}) must be >= {field} ({info.data[field]})")
        return v

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low
```

### HTFBias Model

```python
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
```

### LiquidityLevel Model

```python
class LiquidityLevel(BaseModel):
    """An identified external liquidity pool."""
    level_id: str                # UUID
    liquidity_type: LiquidityType   # BSL or SSL
    source: LiquiditySource
    price: float                 # exact price of the level
    timeframe: Timeframe         # timeframe on which it was identified
    formed_at: datetime          # when the level was created
    strength_score: float        # 0.01.0; higher = more significant
    touch_count: int             # number of times price has tested this level
    swept: bool = False          # True once price has traded through it
    swept_at: Optional[datetime] = None
    # For equal highs/lows: the tolerance band
    band_high: Optional[float] = None
    band_low: Optional[float] = None
```

### PDArray Model

```python
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
    strength_score: float        # 0.01.0
    # For OB: the specific candle that is the order block
    ob_candle_open: Optional[float] = None
    ob_candle_close: Optional[float] = None
    # For Breaker: reference to the original OB it was derived from
    source_ob_id: Optional[str] = None
    # For BPR: references to the two FVGs that form it
    bpr_bullish_fvg_id: Optional[str] = None
    bpr_bearish_fvg_id: Optional[str] = None
    # For CISD level: the open of the first candle in the violated sequence
    cisd_sequence_open: Optional[float] = None
```

### CRT Phase Result

```python
class CRTPhaseResult(BaseModel):
    """CRT phase classification for a single timeframe."""
    timeframe: Timeframe
    phase: CRTPhase
    c1_range_high: Optional[float] = None   # C1 accumulation range top
    c1_range_low: Optional[float] = None    # C1 accumulation range bottom
    c2_close: Optional[float] = None        # C2 manipulation candle close
    c2_within_c1: bool = False              # C2 closed within C1 range
    c2_candle_time: Optional[datetime] = None
    confirmation_tf_cisd: bool = False      # lower-TF CISD confirmed C2
    confidence: float = 0.0                 # 0.01.0
```

### CISD Result

```python
class CISDResult(BaseModel):
    """Result of a CISD detection on a specific timeframe."""
    timeframe: Timeframe
    confirmed: bool
    direction: Optional[BiasDirection] = None   # direction of the CISD
    level: Optional[float] = None               # the open of the first candle in sequence
    sequence_start_time: Optional[datetime] = None
    violation_candle_time: Optional[datetime] = None
    has_swing_prerequisite: bool = False        # 3-candle swing point present

class CISDCascadeStatus(BaseModel):
    """CISD cascade validation across the timeframe hierarchy."""
    trigger_timeframe: Timeframe
    confirmation_timeframe: Timeframe
    cascade_valid: bool
    trigger_cisd: Optional[CISDResult] = None
    confirmation_cisd: Optional[CISDResult] = None
    # Full cascade chain for multi-TF alignment
    cascade_chain: list[CISDResult] = []
```

### OTE Zone

```python
class OTEZone(BaseModel):
    """Optimal Trade Entry Fibonacci zone."""
    swing_high: float
    swing_low: float
    direction: BiasDirection     # which way the trade is
    fib_0: float                 # 0% = start of displacement
    fib_50: float                # 50% retracement
    fib_62: float                # 62% retracement (OTE zone start)
    fib_705: float               # 70.5%  golden level (highest probability)
    fib_79: float                # 79% retracement (OTE zone end)
    fib_100: float               # 100% = end of displacement
    ote_high: float              # upper boundary of OTE zone
    ote_low: float               # lower boundary of OTE zone
    golden_level: float          # = fib_705
    displacement_leg_start: datetime
    displacement_leg_end: datetime
    # Whether current price is inside the OTE zone
    price_in_ote: bool = False
    current_price: Optional[float] = None
```

### UNICORN Pattern

```python
class UnicornPattern(BaseModel):
    """UNICORN = Breaker Block + FVG overlapping at the same price level."""
    direction: BiasDirection
    breaker_block: PDArray
    fvg: PDArray
    overlap_high: float          # upper boundary of the overlap zone
    overlap_low: float           # lower boundary of the overlap zone
    timeframe: Timeframe
    formed_at: datetime
    # Strength = combined score of breaker + FVG
    strength_score: float
```

### Setup Grade Detail

```python
class SetupGradeDetail(BaseModel):
    """Detailed breakdown of the 8-condition A+ checklist."""
    grade: SetupGrade

    # The 8 conditions
    htf_bias_confirmed: bool          # Condition 1
    draw_on_liquidity_identified: bool # Condition 2
    liquidity_sweep_confirmed: bool    # Condition 3
    displacement_present: bool         # Condition 4
    cisd_confirmed: bool               # Condition 5
    entry_pd_array_present: bool       # Condition 6
    stop_placement_valid: bool         # Condition 7
    time_window_aligned: bool          # Condition 8

    # Supporting detail
    conditions_met: int                # 08
    killzone_window: KillzoneWindow
    entry_array: Optional[PDArray] = None
    entry_array_is_unicorn: bool = False
    entry_array_is_ote: bool = False
    suggested_stop: Optional[float] = None   # beyond the entry PD array
    suggested_entry: Optional[float] = None  # golden level or array midpoint
    grade_reason: str                        # human-readable explanation
```

### LiquidityMap (top-level output)

```python
from typing import Dict, List, Optional
from datetime import datetime

class LiquidityMap(BaseModel):
    """
    Complete liquidity and structure analysis for one instrument at one timestamp.
    This is the primary output of LiquidityMappingEngine.analyze().
    Stored on AgentState.liquidity_map.
    """
    # Identity
    instrument: str
    analyzed_at: datetime        # UTC timestamp of the triggering candle close
    trigger_timeframe: Timeframe # the timeframe that triggered this analysis

    # Layer 1  HTF Bias
    htf_bias: Dict[str, HTFBias]  # key = Timeframe.value string

    # Layer 5  Liquidity Levels
    liquidity_levels: List[LiquidityLevel]
    draw_on_liquidity: Optional[LiquidityLevel] = None  # primary target
    sweep_detected: bool = False                         # sweep of draw_on_liquidity

    # Layer 6  PD Arrays
    pd_arrays: List[PDArray]

    # Layer 3  CRT / IPDA
    crt_phases: Dict[str, CRTPhaseResult]   # key = Timeframe.value string
    cisd_cascade: Optional[CISDCascadeStatus] = None

    # Layer 4  Price Phase
    current_price_phase: Optional[PricePhase] = None

    # Layer 7  Entry Models
    ote_zone: Optional[OTEZone] = None
    unicorn: Optional[UnicornPattern] = None

    # Layer 8  Setup Grade
    setup_grade: SetupGradeDetail

    # Convenience accessors
    def get_bias(self, tf: Timeframe) -> Optional[HTFBias]:
        return self.htf_bias.get(tf.value)

    def get_arrays_by_type(self, array_type: PDArrayType) -> List[PDArray]:
        return [a for a in self.pd_arrays if a.array_type == array_type]

    def get_arrays_in_range(
        self, price_low: float, price_high: float
    ) -> List[PDArray]:
        return [
            a for a in self.pd_arrays
            if not a.is_filled and a.low <= price_high and a.high >= price_low
        ]

    def to_agent_context(self) -> str:
        """
        Serialize the LiquidityMap to a structured string for LLM prompt injection.
        See section: to_agent_context() Output Format.
        """
        ...
```

**Validation Rules**:
- `analyzed_at` must be timezone-aware
- `htf_bias` must contain at least D1 and W1 entries
- `setup_grade.conditions_met` must equal the count of True boolean conditions
- `draw_on_liquidity` must be a member of `liquidity_levels` if set
- `ote_zone.ote_low < ote_zone.ote_high` always
- `unicorn.overlap_low < unicorn.overlap_high` always

---

