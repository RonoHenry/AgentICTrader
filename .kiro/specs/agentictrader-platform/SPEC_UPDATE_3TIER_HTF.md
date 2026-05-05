# Spec Update: 3-Tier HTF Timeframe Correlation (TTrades Methodology)

**Date**: 2026-05-02  
**Status**: Spec Updated, Task 9 Ready for Re-implementation

---

## Summary

Updated the AgentICTrader.AI spec to reflect the **3-tier timeframe correlation structure** based on TTrades Fractal Model methodology, replacing the simple single-level HTF mappings.

---

## Changes Made

### 1. Requirements.md (FR-2)

**Before**: Simple single-level mappings (M1→M5, M5→M15, etc.)

**After**: Comprehensive 3-tier structure with:

#### FR-2.1: 3-Tier Timeframe Correlation
- **Higher TF (Bias Layer)**: Determines market direction via Candle 2 closures and Candle 3 expansions
- **Mid TF (Structure Layer)**: Confirms alignment via CISD or market structure shift
- **Lower TF (Entry Layer)**: Precision timing for entry

**Trading Style-Specific Correlations:**

| Trading Style | Higher TF (Bias) | Mid TF (Structure) | Lower TF (Entry) |
|---------------|------------------|-------------------|------------------|
| Scalping      | H1               | M15               | M1               |
| Intraday Standard | D1          | H1                | M5               |
| Intraday Simple | D1            | H4                | M15              |
| Swing Trading | W1               | D1                | H1 or H4         |
| Position/Crypto | MN1            | W1                | H4               |

**Supported Timeframes**: M1, M3, M5, M15, M30, H1, H4, D1, W1, MN1

#### FR-2.2: Candle Numbering System (TTFM)
- Candle 1 (Setup): Establishes range
- Candle 2 (Reversal/Manipulation): Sweep + closure inside range
  - Small wick → trade Candle 2 expansion
  - Large wick → wait for Candle 3
- Candle 3 (Expansion/Distribution): Aggressive move to liquidity target

#### FR-2.3: Change in State of Delivery (CISD)
- Bullish CISD: Sweep low, close above last down-close open
- Bearish CISD: Sweep high, close below last up-close open
- Must occur inside Higher TF Candle 2/3 structure

#### FR-2.4: HTF Projection Levels
- HTF Open (bias anchor), HTF High (upper boundary), HTF Low (lower boundary)
- Compute price position, range proximity percentages
- Store in TimescaleDB indicators table

#### FR-2.5: Expansion Sync Principle
- All three timeframes must expand in same direction for highest probability
- "Wick Concept": wait for wrong direction first, then enter on body expansion

### 2. Requirements.md (FR-1)

**Updated timeframes**: M1, M3, M5, M15, M30, H1, H4, D1, W1, MN1 (added M3, M30, MN1)

### 3. Design.md

**Updated** "Sole Technical Indicator" section to include:
- 3-tier structure explanation
- Trading style correlations table
- Candle Numbering System (TTFM)
- CISD definition

### 4. Tasks.md (Task 9)

**Before**: Simple single-level HTF selector with `get_htf_timeframe()` and `get_htf_timeframes()`

**After**: 3-tier correlation system with:

**Functions to implement:**
- `get_htf_correlation(current_tf: str, trading_style: TradingStyle) -> tuple[str, str, str]`
- `get_bias_timeframe(current_tf: str, trading_style: TradingStyle) -> str`
- `get_structure_timeframe(current_tf: str, trading_style: TradingStyle) -> str`
- `get_entry_timeframe(current_tf: str, trading_style: TradingStyle) -> str`
- `TradingStyle` enum: SCALPING, INTRADAY_STANDARD, INTRADAY_SIMPLE, SWING, POSITION
- `SUPPORTED_TIMEFRAMES` constant

**Test requirements:**
- All trading style correlations return correct 3-tier tuples
- Individual layer extraction functions work correctly
- All timeframes supported: M1, M3, M5, M15, M30, H1, H4, D1, W1, MN1
- Invalid inputs raise ValueError
- Property test: strict timeframe hierarchy (bias > structure > entry)

---

## Next Steps

1. **Delete old implementation**:
   - `ml/features/htf_selector.py` (old version)
   - `backend/tests/test_htf_selector.py` (old version)

2. **Re-implement Task 9** following the updated spec:
   - Write new failing tests based on 3-tier requirements
   - Implement 3-tier correlation logic
   - Verify all tests pass

3. **Update dependent tasks** (if any reference the old API):
   - Task 10: HTF OHLC computation
   - Task 14: Feature pipeline orchestration

---

## Key Concepts from TTrades Methodology

### The 3-Question Framework
Every trade reasoning must answer:
1. **Where has price come from?** (HTF context, previous session range, PD arrays)
2. **Where is it now?** (current time window phase, price vs reference opens)
3. **Where is it likely to go?** (nearest liquidity pool or imbalance to rebalance)

### Entry Bias Rules
- **Bullish setup**: Prefer entries BELOW session/candle open (manipulation wick down first, then expansion up)
- **Bearish setup**: Prefer entries ABOVE session/candle open (manipulation wick up first, then expansion down)

### Expansion Sync
Highest probability trades occur when Daily, Hourly, and 5-minute charts are ALL expanding in the same direction.

### The Wick Concept
On every timeframe, wait for price to trade in the "wrong" direction first (forming the wick) before it reverses into the "true" move (the body expansion).

---

## Files Modified

1. `.kiro/specs/agentictrader-platform/requirements.md` - FR-1, FR-2 completely rewritten
2. `.kiro/specs/agentictrader-platform/design.md` - HTF section updated
3. `.kiro/specs/agentictrader-platform/tasks.md` - Task 9 rewritten

---

## Implementation Status

- [x] Spec updated with 3-tier methodology
- [x] Old Task 9 implementation replaced with 3-tier system
- [x] New Task 9 implementation (3-tier) - **COMPLETED** (44/44 tests passing)
