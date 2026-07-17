# Design Document — CISD Analyzer

## Overview

The CISD Analyzer (`backend/trader/agents/cisd.py`) is a timeframe-agnostic detector of the
TTrades reversal confirmation sequence: **Turtle Soup sweep → imbalance (FVG or IFVG) →
CISD validating Order Block**. It implements Requirement 6 of the liquidity-engine spec at the
component level and satisfies BRD traceability points BR-ML03 and BR-AG01.

The detector is deliberately stateless. Each `scan()` call accepts a raw candle list (plus an
optional rolling FVG history buffer) and returns a single `CISDResult` dataclass. Callers own
all persistent state. Because price structure is fractal, the same code handles both HTF bias
validation (H1/H4/D1) and LTF entry gating (M1/M5/M15) without any timeframe branching.

The `sequence_step` field (0–3) encodes how far through the three-step pattern price has
progressed, giving the confluence scorer a graded feature rather than a binary pass/fail.

---

## Architecture

The analyzer sits inside the `backend/trader/agents/` package and is called from two separate
locations in the broader agent pipeline.

```
HTF Bias Validation (H1/H4/D1)
    ZoneFeatureExtractor  ──scan(htf_candles, fvg_history)──►  CISDAnalyzer
    CISDAnalyzer          ──confirmed=True──►  htf_trend_bias = direction
    CISDAnalyzer          ──confirmed=False──►  _derive_htf_trend_bias() (fallback)

LTF Entry Gate (M1/M5/M15)
    decide_node           ──scan(ltf_candles)──►  CISDAnalyzer
    CISDAnalyzer          ──sequence_step──►  confluence gate
                              step=3  → full pass
                              step=2  → partial (confidence reduction)
                              step≤1  → gate failed

Cross-cutting
    CISDResult.sequence_step ──►  Confluence Scorer (graded feature)
    CISDResult               ──►  AgentState.cisd_sequence_step (logging + learn_node)
```

### Position in the Broader System

| Layer | Component | Role |
|---|---|---|
| Feature extraction | `ZoneFeatureExtractor` | Calls CISDAnalyzer on HTF candles; uses result to set `htf_trend_bias` |
| Decision gate | `decide_node` | Calls CISDAnalyzer on LTF candles; uses `sequence_step` as confluence gate |
| ML features | Confluence Scorer | Consumes `sequence_step` (0–3) as a graded feature |
| State persistence | `AgentState` | Records `cisd_sequence_step` for logging and learn_node samples |
| FVG history | Caller-owned buffer | Callers pass `fvg_history: List[FVGZone]` to enable IFVG detection |

---

## Components and Interfaces

### `FVGZone` — Rolling History Buffer Entry

```python
@dataclass
class FVGZone:
    high: float           # Upper boundary; enforced high > low in __post_init__
    low: float            # Lower boundary
    direction: str        # "BULLISH" | "BEARISH" — enforced in __post_init__
    is_filled: bool       # True when price has fully traded through the gap
    candle_index: int     # Index of the third candle (candles[i]) that formed the gap
```

`__post_init__` raises `ValueError` if `high <= low` or `direction` is outside the allowed set.
Callers never construct `FVGZone` objects manually; they receive them from `update_fvg_history`.

---

### `CISDResult` — Scan Output Dataclass

```python
@dataclass
class CISDResult:
    confirmed: bool = False                  # True only when all 3 steps satisfied
    direction: str = "NONE"                  # "BULLISH" | "BEARISH" | "NONE"
    sequence_step: int = 0                   # 0–3
    sweep_level: Optional[float] = None      # Swing price that was swept
    sweep_direction: Optional[str] = None    # "BULLISH" | "BEARISH" | None
    imbalance_type: Optional[str] = None     # "FVG" | "IFVG" | None
    imbalance_high: Optional[float] = None   # Upper bound of imbalance zone
    imbalance_low: Optional[float] = None    # Lower bound of imbalance zone
    ob_high: Optional[float] = None          # OB body upper boundary
    ob_low: Optional[float] = None           # OB body lower boundary
    candles_elapsed: int = 0                 # Candles since sweep was detected
```

Field dependency rules (invariants enforced by tests):

| Condition | Required field state |
|---|---|
| `confirmed=True` | `sequence_step=3`, `direction ≠ "NONE"`, `ob_high > ob_low` |
| `sequence_step < 2` | `imbalance_type`, `imbalance_high`, `imbalance_low` all `None` |
| `sequence_step < 3` | `ob_high`, `ob_low` both `None` |
| `sequence_step = 0` | `sweep_level`, `sweep_direction` both `None` |

---

### `CISDAnalyzer` — Main Class

```python
class CISDAnalyzer:
    def __init__(self, max_sequence_candles: int = 20) -> None: ...

    def scan(
        self,
        candles: List[Dict[str, Any]],
        fvg_history: Optional[List[FVGZone]] = None,
    ) -> CISDResult: ...

    def update_fvg_history(
        self, candles: List[Dict[str, Any]]
    ) -> List[FVGZone]: ...

    # Private helpers
    def _find_last_swing_high(self, candles, end_idx: int) -> Optional[float]: ...
    def _find_last_swing_low(self, candles, end_idx: int) -> Optional[float]: ...
    def _find_order_block(
        self,
        candles,
        sweep_direction: Optional[str],
        before_idx: Optional[int],
    ) -> Optional[tuple]: ...
```

**`scan()` contract:**
- Read-only: never mutates any input candle dict
- Empty or `< 3` candle list returns `CISDResult()` (all defaults, `sequence_step=0`)
- Returns immediately on the first confirmed CISD; otherwise returns partial progress

**`update_fvg_history()` contract:**
- Returns a fresh list each call; uses a deduplication set to prevent duplicates from repeated
  calls on the same window
- Callers are responsible for merging or replacing their stored history

---

## Data Models

### Candle Dictionary (input)

The analyzer accepts standard OHLC dicts — the same format used everywhere in the project.
No timeframe field is inspected or required.

```python
candle: Dict[str, Any] = {
    "open":  float,   # required
    "high":  float,   # required
    "low":   float,   # required
    "close": float,   # required
    # any extra fields (e.g. "time", "volume") are ignored
}
```

### FVGZone (persisted by callers)

See Components section. Callers receive a list of `FVGZone` objects from
`update_fvg_history()` and pass the same list (or an accumulated version) to the next
`scan()` call as `fvg_history`.

### CISDResult (returned per scan)

A plain immutable dataclass. `confirmed` is the primary routing flag; `sequence_step` is the
graded feature consumed by the confluence scorer.

---

## Algorithm Design

### Step 1: Turtle Soup Sweep Detection

A sweep is detected when the current candle's wick breaks a prior swing level but the candle
closes back inside the range — a classic stop hunt / false breakout pattern.

**Bullish sweep** (seeks long liquidity, reversal up expected):
```
candle.low   < swing_low     # wick pierces swing low
candle.close > swing_low     # close back above — no follow-through
→ sweep_direction = "BULLISH", sweep_level = swing_low
```

**Bearish sweep** (seeks short liquidity, reversal down expected):
```
candle.high  > swing_high    # wick pierces swing high
candle.close < swing_high    # close back below
→ sweep_direction = "BEARISH", sweep_level = swing_high
```

The analyzer uses the **most recent** swing point found via backward search.

### Swing Point Detection (1-Candle Fractal)

```
Swing High at index i:  candles[i].high > candles[i-1].high  AND  candles[i].high > candles[i+1].high
Swing Low  at index i:  candles[i].low  < candles[i-1].low   AND  candles[i].low  < candles[i+1].low
```

The helpers `_find_last_swing_high(candles, end_idx)` and `_find_last_swing_low(candles, end_idx)`
search backward from `end_idx - 2` to 1, returning the first match. They require
`end_idx >= 3` — fewer candles returns `None`.

### Step 2: Imbalance Detection

**FVG Path (inline detection):**

Detection only runs when `i >= sweep_candle_idx + 2` (at least 2 candles after the sweep).

```
Bullish FVG: candles[i-2].high < candles[i].low
    → imbalance_low  = candles[i-2].high
    → imbalance_high = candles[i].low
    → displacement_candle_idx = i - 1

Bearish FVG: candles[i-2].low > candles[i].high
    → imbalance_high = candles[i-2].low
    → imbalance_low  = candles[i].high
    → displacement_candle_idx = i - 1
```

**IFVG Path (from history buffer):**

When no FVG is found and `fvg_history` is non-empty, the analyzer walks the history looking
for an opposing zone that the displacement candle overlaps:

```
BULLISH sweep → look for zone.direction == "BEARISH"
    price overlap: candle.low <= zone.high AND candle.high >= zone.low
    → imbalance_type = "IFVG", displacement_candle_idx = i
```

**Preference rule:** FVG takes precedence over IFVG when both are detectable in the same move.

A successful imbalance detection requires `imbalance_high > imbalance_low` before advancing
to `sequence_step = 2`.

### Step 3: CISD Validating Order Block

**Order Block identification** (`_find_order_block`):

Searches backward from `displacement_candle_idx - 1`:
```
BULLISH sequence: last candle where close < open  (bearish / down-close)
BEARISH sequence: last candle where close > open  (bullish / up-close)
OB body = (max(open, close),  min(open, close))   → (ob_high, ob_low)
```

**Confirmation trigger:**

```
ob_low <= candle.close <= ob_high  →  CISD confirmed
```

When confirmed, `scan()` returns immediately with `confirmed=True`, `sequence_step=3`, and
all fields populated.

### Sequence Expiry

The `candles_elapsed` counter starts at 0 on the sweep candle and increments by 1 for every
subsequent candle while `sequence_step >= 1`.

```
candles_elapsed > max_sequence_candles  →  reset all state, return to step 0
```

The expiry check happens at the **start** of each iteration — before any step logic — so an
expired sequence cannot inadvertently match on the expiry candle itself.

---

## Correctness Properties

### Property 1: `confirmed` and `sequence_step` are mutually consistent (Invariant)

For any candle list and any `fvg_history`, `scan()` SHALL produce a `CISDResult` where
`confirmed = True` if and only if `sequence_step = 3`.

**Validates: Requirements 9.1, 9.2**

---

### Property 2: Enum-valued fields contain only allowed values (Invariant)

For any input to `scan()`, the returned `CISDResult` SHALL satisfy:
- `direction ∈ {"BULLISH", "BEARISH", "NONE"}`
- `sequence_step ∈ {0, 1, 2, 3}`
- `sweep_direction ∈ {"BULLISH", "BEARISH", None}`
- `imbalance_type ∈ {"FVG", "IFVG", None}`
- `candles_elapsed >= 0`

**Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**

---

### Property 3: `confirmed=True` implies `direction ≠ "NONE"` (Invariant)

For any `CISDResult` where `confirmed = True`, `direction` SHALL never equal `"NONE"`.

**Validates: Requirements 9.3**

---

### Property 4: Imbalance fields are `None` below step 2 (Field-Dependency Invariant)

For any `CISDResult` where `sequence_step < 2`, `imbalance_type`, `imbalance_high`, and
`imbalance_low` SHALL all be `None`.

**Validates: Requirements 9.4, 9.5**

---

### Property 5: OB fields are `None` below step 3 (Field-Dependency Invariant)

For any `CISDResult` where `sequence_step < 3`, `ob_high` and `ob_low` SHALL both be `None`.

**Validates: Requirements 9.6** Sweep fields are `None` at step 0 (Field-Dependency Invariant)

For any `CISDResult` where `sequence_step = 0`, `sweep_level` and `sweep_direction` SHALL
both be `None`.

**Validates: Requirements 9.7**

---

### Property 7: `ob_high > ob_low` when confirmed (Invariant)

For any `CISDResult` where `confirmed = True`, `ob_high` SHALL be strictly greater than
`ob_low`, and neither SHALL be `None`.

**Validates: Requirements 8.4, 9.6**

---

### Property 8: `scan()` and `update_fvg_history()` never mutate input candles (Immutability)

For any candle list passed to either method, every candle dictionary SHALL have exactly the
same key-value pairs after the call as before the call.

**Validates: Requirements 3.6, 12.3**

---

### Property 9: `update_fvg_history` is idempotent (Idempotence)

For any candle list `C`, calling `update_fvg_history(C)` twice SHALL return lists with the
same set of `(high, low, direction, candle_index)` combinations — no duplicates introduced.

**Validates: Requirements 12.4**

---

### Property 10: `FVGZone.high > FVGZone.low` for all returned zones (Invariant)

For any `FVGZone` returned by `update_fvg_history()`, `high` SHALL be strictly greater than
`low`.

**Validates: Requirements 2.3, 12.2**

---

### Property 11: `imbalance_high > imbalance_low` when step ≥ 2 (Invariant)

For any `CISDResult` where `sequence_step >= 2` and `imbalance_high` is not `None`,
`imbalance_high` SHALL be strictly greater than `imbalance_low`.

**Validates: Requirements 6.4, 7.2**

---

## Error Handling

### Input Validation

`scan()` applies two structural guards and returns a default `CISDResult` rather than raising:

```python
if not candles:          # empty list → step 0
if len(candles) < 3:     # fewer than structural minimum → step 0
```

This is intentional — an empty or too-short window is normal (startup, sparse data), not an
exception. Callers need no `try/except` around the scan call.

### `FVGZone` Construction Guard

`FVGZone.__post_init__` raises `ValueError` for `high <= low` or invalid direction. Because
`update_fvg_history()` already ensures `high > low` before constructing zones, this guard
acts as a safety net.

### Sequence Expiry

Expiry (`candles_elapsed > max_sequence_candles`) is normal operation, not an error. Result
after expiry is always a clean `sequence_step=0` with all partial fields as `None`.

### Float Precision

All OHLC values are cast to `float` on access (`float(c["high"])`). No explicit precision
rounding is performed inside the analyzer.

### Missing OHLC Keys

The implementation does not do defensive key-checking. If a caller passes candle dicts
missing required keys, a `KeyError` propagates. Callers should validate candle format
upstream. The contract is `{open, high, low, close}`.

---

## Testing Strategy

Test file: `backend/tests/test_cisd_analyzer.py`

Coverage target: **≥ 95%** (agent nodes domain per project TDD standards).

### Unit Tests (example-based)

**Structural / smoke:**
- Import `CISDAnalyzer`, `CISDResult`, `FVGZone` from `backend.trader.agents.cisd`
- Verify dataclass field names and defaults on `CISDResult`
- Verify `FVGZone.__post_init__` raises for `high <= low` and invalid direction

**Edge cases — `scan()`:**
- Empty list → default `CISDResult` (step=0, confirmed=False)
- 1- and 2-candle lists → default `CISDResult`
- No detectable swing points → step=0
- Sweep only (no FVG) → step=1
- Sweep + FVG, no OB close → step=2
- Complete bullish 3-step CISD → confirmed=True, direction="BULLISH"
- Complete bearish 3-step CISD → confirmed=True, direction="BEARISH"
- FVG preferred over IFVG when both detectable
- Sequence expires at exactly `max_sequence_candles + 1` → step=0

**Edge cases — `update_fvg_history()`:**
- Empty candles → empty list
- 2-candle input → empty list
- No FVG gap → empty list
- Clear bullish FVG → one zone with direction="BULLISH"
- Clear bearish FVG → one zone with direction="BEARISH"

**Integration contracts:**
- confirmed=True + direction="BULLISH" → ZoneFeatureExtractor sets htf_trend_bias="BULLISH"
- confirmed=False → ZoneFeatureExtractor falls back to `_derive_htf_trend_bias()`
- sequence_step=3 → decide_node: gate fully passed
- sequence_step=2 → decide_node: partial pass with confidence reduction
- sequence_step≤1 → decide_node: gate failed, surfaced in decision_reason

### Property-Based Tests (Hypothesis — `@pytest.mark.property`)

All 11 design properties are implemented as Hypothesis tests with `max_examples=200`.

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@st.composite
def candle(draw, min_price=1.0, max_price=2.0):
    low   = draw(st.floats(min_value=min_price, max_value=max_price))
    high  = draw(st.floats(min_value=low, max_value=max_price))
    open_ = draw(st.floats(min_value=low, max_value=high))
    close = draw(st.floats(min_value=low, max_value=high))
    return {"open": open_, "high": high, "low": low, "close": close}

candle_list = st.lists(candle(), min_size=0, max_size=50)
```

Example property test outline:

```python
@pytest.mark.property
@given(candles=candle_list)
@settings(max_examples=200)
def test_confirmed_iff_step3(candles):
    """Feature: cisd-analyzer, Property 1: confirmed iff sequence_step==3"""
    result = CISDAnalyzer().scan(candles)
    assert result.confirmed == (result.sequence_step == 3)
```

### Running the Tests

```bash
# All CISD analyzer tests
pytest backend/tests/test_cisd_analyzer.py -v

# Property tests only
pytest backend/tests/test_cisd_analyzer.py -m property -v

# With coverage
pytest backend/tests/test_cisd_analyzer.py --cov=backend/trader/agents/cisd --cov-report=term-missing
```
