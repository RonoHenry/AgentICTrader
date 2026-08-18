"""
Setup quality grading — the deterministic 8-condition A+/A/B/NO_TRADE grade.

The 8 boolean conditions are read straight off `LiquidityMap`; `grade()`
returns the full `SetupGradeDetail` (not just the bare `SetupGrade` enum)
since that's what `LiquidityMap.setup_grade` actually stores and what
`grade_reason`/`suggested_entry`/`suggested_stop` need to be computed once,
consistently, alongside the grade itself.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from liquidity_engine.models import (
    BiasDirection,
    LiquidityMap,
    PDArray,
    PDArrayType,
    SetupGrade,
    SetupGradeDetail,
    Timeframe,
)
from liquidity_engine.utils.time_utils import is_in_killzone

# Stop is placed this fraction of the entry array's own range beyond its far
# boundary — a stop sitting exactly on the boundary isn't "beyond" it.
_STOP_BUFFER_RATIO = 0.1

# HTF PD arrays (D1/W1/H4/...) inform bias and the draw-on-liquidity target,
# but are not where an entry is actually taken from — a wide HTF Breaker or
# BPR can carry a higher strength_score than a precise LTF FVG purely by
# array-type weighting (see PDArrayDetector._assign_strength_score, which is
# type-only, not timeframe-aware), which previously let entry/stop get
# selected from a zone nowhere near live price. Entry array selection is
# restricted to M15-and-below; HTF arrays still count for _check_displacement
# (evidence an expansion move happened, regardless of which timeframe shows
# it) since that's about confirming institutional footprint, not entry
# mechanics.
_ENTRY_ELIGIBLE_TIMEFRAMES = frozenset({Timeframe.M1, Timeframe.M3, Timeframe.M5, Timeframe.M15})


class SetupGrader:
    """Evaluates the 8 A+ conditions and assigns a deterministic setup grade."""

    def grade(self, liquidity_map: LiquidityMap, timestamp: datetime) -> SetupGradeDetail:
        htf_bias_confirmed = self._check_htf_bias(liquidity_map)
        draw_on_liquidity_identified = self._check_draw_on_liquidity(liquidity_map)
        liquidity_sweep_confirmed = self._check_liquidity_sweep(liquidity_map)
        displacement_present = self._check_displacement(liquidity_map)
        cisd_confirmed = self._check_cisd(liquidity_map)
        entry_pd_array_present = self._check_entry_pd_array(liquidity_map)
        stop_placement_valid = self._check_stop_placement(liquidity_map)
        time_window_aligned = self._check_time_window(liquidity_map, timestamp)

        conditions_met = sum(
            (
                htf_bias_confirmed,
                draw_on_liquidity_identified,
                liquidity_sweep_confirmed,
                displacement_present,
                cisd_confirmed,
                entry_pd_array_present,
                stop_placement_valid,
                time_window_aligned,
            )
        )

        entry_array = self._select_entry_array(liquidity_map)
        grade = self._assign_grade(
            liquidity_map,
            conditions_met,
            htf_bias_confirmed,
            draw_on_liquidity_identified,
            liquidity_sweep_confirmed,
            cisd_confirmed,
            entry_pd_array_present,
        )

        return SetupGradeDetail(
            grade=grade,
            conditions_met=conditions_met,
            htf_bias_confirmed=htf_bias_confirmed,
            draw_on_liquidity_identified=draw_on_liquidity_identified,
            liquidity_sweep_confirmed=liquidity_sweep_confirmed,
            displacement_present=displacement_present,
            cisd_confirmed=cisd_confirmed,
            entry_pd_array_present=entry_pd_array_present,
            stop_placement_valid=stop_placement_valid,
            time_window_aligned=time_window_aligned,
            grade_reason=self._build_grade_reason(liquidity_map, grade, conditions_met, entry_array),
            suggested_entry=self._suggested_entry(liquidity_map, entry_array),
            suggested_stop=self._suggested_stop(entry_array),
            entry_array_high=entry_array.high if entry_array is not None else None,
            entry_array_low=entry_array.low if entry_array is not None else None,
            entry_array_direction=entry_array.direction if entry_array is not None else None,
        )

    def _check_htf_bias(self, lm: LiquidityMap) -> bool:
        d1 = lm.htf_bias.get(Timeframe.D1.value)
        w1 = lm.htf_bias.get(Timeframe.W1.value)
        if d1 is None or w1 is None:
            return False
        return d1.direction != BiasDirection.NEUTRAL and w1.direction != BiasDirection.NEUTRAL

    def _check_draw_on_liquidity(self, lm: LiquidityMap) -> bool:
        return lm.draw_on_liquidity is not None

    def _check_liquidity_sweep(self, lm: LiquidityMap) -> bool:
        return lm.sweep_detected

    def _check_displacement(self, lm: LiquidityMap) -> bool:
        # Deliberately independent of FVG presence: the B grade (Requirement
        # 9.4) is specifically "sweep + CISD + an FVG-only entry array, no
        # Breaker/UNICORN" — if displacement were satisfied by that same FVG,
        # conditions_met would always reach 7 in exactly the scenario B is
        # meant to describe, making B unreachable. An Order Block is the
        # actual expansion-move footprint, so it's used here instead.
        return any(a.array_type == PDArrayType.OB for a in lm.pd_arrays)

    def _check_cisd(self, lm: LiquidityMap) -> bool:
        return lm.cisd_cascade is not None and lm.cisd_cascade.cascade_valid

    def _entry_eligible_arrays(self, lm: LiquidityMap) -> List[PDArray]:
        """Unfilled PD arrays on M15-and-below only — see module-level
        _ENTRY_ELIGIBLE_TIMEFRAMES docstring for why HTF arrays are excluded
        here specifically."""
        return [
            a for a in lm.pd_arrays
            if not a.is_filled and a.timeframe in _ENTRY_ELIGIBLE_TIMEFRAMES
        ]

    def _check_entry_pd_array(self, lm: LiquidityMap) -> bool:
        return bool(self._entry_eligible_arrays(lm))

    def _check_stop_placement(self, lm: LiquidityMap) -> bool:
        # A stop is placed relative to the same array used for entry, so
        # validity is coupled to an entry array actually being available.
        return self._check_entry_pd_array(lm)

    def _check_time_window(self, lm: LiquidityMap, ts: datetime) -> bool:
        return is_in_killzone(ts)

    def _select_entry_array(self, lm: LiquidityMap) -> Optional[PDArray]:
        unfilled = self._entry_eligible_arrays(lm)
        if not unfilled:
            return None
        return max(unfilled, key=lambda a: a.strength_score)

    def _assign_grade(
        self,
        lm: LiquidityMap,
        conditions_met: int,
        htf_bias_confirmed: bool,
        draw_on_liquidity_identified: bool,
        liquidity_sweep_confirmed: bool,
        cisd_confirmed: bool,
        entry_pd_array_present: bool,
    ) -> SetupGrade:
        if not htf_bias_confirmed or not draw_on_liquidity_identified:
            return SetupGrade.NO_TRADE
        if conditions_met < 6:
            return SetupGrade.NO_TRADE
        if conditions_met == 8:
            return SetupGrade.A_PLUS
        if conditions_met == 7:
            return SetupGrade.A
        if self._b_grade_eligible(lm, liquidity_sweep_confirmed, cisd_confirmed, entry_pd_array_present):
            return SetupGrade.B
        return SetupGrade.NO_TRADE

    def _b_grade_eligible(
        self, lm: LiquidityMap, sweep: bool, cisd: bool, entry_present: bool
    ) -> bool:
        if not (sweep and cisd and entry_present):
            return False
        # B-grade characterizes the entry array itself (FVG-only, no
        # Breaker/UNICORN) — scoped to the same LTF-eligible pool
        # _select_entry_array draws from, not every array on every
        # timeframe supplied.
        entry_eligible = self._entry_eligible_arrays(lm)
        has_breaker = any(a.array_type == PDArrayType.BREAKER for a in entry_eligible)
        has_unicorn = lm.unicorn is not None
        has_fvg = any(a.array_type == PDArrayType.FVG for a in entry_eligible)
        return has_fvg and not has_breaker and not has_unicorn

    def _suggested_entry(self, lm: LiquidityMap, entry_array: Optional[PDArray]) -> Optional[float]:
        if entry_array is None:
            return None
        entry_array_is_ote = (
            lm.ote_zone is not None
            and entry_array.low <= lm.ote_zone.ote_high
            and lm.ote_zone.ote_low <= entry_array.high
        )
        if entry_array_is_ote:
            return lm.ote_zone.golden_level
        return (entry_array.high + entry_array.low) / 2

    def _suggested_stop(self, entry_array: Optional[PDArray]) -> Optional[float]:
        if entry_array is None:
            return None
        buffer = (entry_array.high - entry_array.low) * _STOP_BUFFER_RATIO
        if entry_array.direction == BiasDirection.BEARISH:
            return entry_array.high + buffer
        return entry_array.low - buffer

    def _build_grade_reason(
        self,
        lm: LiquidityMap,
        grade: SetupGrade,
        conditions_met: int,
        entry_array: Optional[PDArray],
    ) -> str:
        parts: List[str] = [f"Grade {grade.value} ({conditions_met}/8 conditions met)."]
        if entry_array is not None and entry_array.structure_confirmed:
            parts.append(
                "Entry array is structure-confirmed (sweep followed by a structural break back "
                "through the prior swing)."
            )
        if lm.fractal_model is not None:
            stance = "above" if lm.fractal_model.price_above_equilibrium else "at or below"
            parts.append(f"Price is {stance} the Fractal Model equilibrium.")
        return " ".join(parts)
