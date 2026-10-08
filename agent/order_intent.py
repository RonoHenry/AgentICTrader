"""The order the live runner and AlgoBacktester derive from a graded setup.

build_order_intent() is the decision code both run (.kiro/specs/
algo-backtester, task 190): it was _process_instrument's grade -> order
step in scripts/run_live_agent.py, moved here unchanged except for the
setup id. Because the runner and the backtester's Phase A call the same
function, a backtest makes the decisions the agent makes live (Req 1.2).

A setup's id is derived from its entry PD array instead of a fresh uuid4()
per pass (task 189), so re-grading the same array on the next bar yields
the same setup. That identity is what allows one attempt per setup (D6)
and duplicate-order protection.

The direction, stop and targets come from the setup sequence the grader
read (liquidity-engine update 2026-10): the sequence's direction, the stop
behind its protected swing (cfg.stop_mode), and TP1 at an SD level of its
setup leg.

The candle anticipation policy (update 2026-10b) runs after the grade gates
and before the stop checks; the first rule a setup fails names its NoTrade:
the anticipated direction (bias_mode), the false move (require_false_move),
the manipulation window (time_window), the higher-timeframe POI
(require_htf_poi). Then the stop must be beyond the entry and at least
min_stop_spreads typical spreads away, and TP1 may be the profile's draw
when it is nearer (target_mode).

Validates: Requirements 1.2, 1.3 (.kiro/specs/algo-backtester/requirements.md);
Requirements 19, 23, 25.2 (.kiro/specs/liquidity-engine/requirements.md)
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from agent.strategy_config import BiasMode, StopMode, StrategyConfig, TargetMode, TimeWindow
from liquidity_engine.models import BiasDirection, Candle, LiquidityMap, SetupGrade, SetupSequence, Timeframe
from liquidity_engine.utils.id_utils import deterministic_id
from ml.features.session_features import TimeFeatures, TimeWindowClassifier

__all__ = ["OWN_DECISION_REASONS", "NoTrade", "OrderIntent", "build_order_intent", "setup_id_for"]

Direction = Literal["LONG", "SHORT"]
NoTradeReason = Literal[
    "NO_GRADE", "NO_TRADE", "RR_BELOW_MIN", "INVALID_STOP",
    "NO_ANTICIPATION", "AGAINST_PROFILE", "NO_FALSE_MOVE", "OUTSIDE_WINDOW", "NO_POI", "STOP_TOO_TIGHT",
]
#: Reasons the backtest journal records as their own decision rather than NO_TRADE
#: (liquidity-engine Req 23.6): a graded setup refused by a rule, not by the grader.
OWN_DECISION_REASONS = (
    "RR_BELOW_MIN", "INVALID_STOP",
    "NO_ANTICIPATION", "AGAINST_PROFILE", "NO_FALSE_MOVE", "OUTSIDE_WINDOW", "NO_POI", "STOP_TOO_TIGHT",
)
_POI_TIMEFRAMES = (Timeframe.H4, Timeframe.D1)


@dataclass(frozen=True)
class OrderIntent:
    setup_id: str
    instrument: str
    entry_tf: Timeframe
    as_of: datetime
    grade: SetupGrade
    direction: Direction
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float]
    r_ratio: float
    confidence: float
    time_features: TimeFeatures
    patterns: tuple[dict, ...]
    regime: str

    def to_message(self, mode: str, detected_at: Optional[datetime] = None) -> dict:
        """The AgentGraph message the runner sends, without candles_by_tf.
        The live runner adds the candle window itself, so observe_node can
        run the AI layers; the backtester leaves it out, which skips
        observe_node's second engine run.

        ``detected_at`` is when the setup was detected, which observe_node's
        staleness check measures from. It defaults to as_of: a backtest
        detects at t. Live detection happens after the bar closed, so the
        runner passes the wall-clock time of the hand-off."""
        tf = self.time_features
        return {
            "setup_id": self.setup_id,
            "instrument": self.instrument,
            "timeframe": self.entry_tf.value,
            "direction": self.direction,
            "raw_confidence": self.confidence,
            "detected_at": (detected_at or self.as_of).isoformat(),
            "regime": self.regime,
            "patterns": [dict(p) for p in self.patterns],
            "mode": getattr(mode, "value", mode),
            "trade_plan": {
                "entry": self.entry,
                "stop_loss": self.stop_loss,
                "take_profit_1": self.take_profit_1,
                "take_profit_2": self.take_profit_2,
                "r_ratio": self.r_ratio,
                "recommended_size": 0.01,
            },
            "time_window": tf.time_window,
            "narrative_phase": tf.narrative_phase,
            "time_window_weight": tf.time_window_weight,
            "is_killzone": tf.is_killzone,
            "price_vs_daily_open": tf.price_vs_daily_open,
            "price_vs_weekly_open": tf.price_vs_weekly_open,
        }


@dataclass(frozen=True)
class NoTrade:
    instrument: str
    as_of: datetime
    grade: str             # "NO_TRADE", or the letter grade of a setup with no valid stop or short of min R:R
    reason: NoTradeReason
    detail: str = ""       # the grader's reason, or the R:R shortfall
    r_ratio: Optional[float] = None


def setup_id_for(instrument: str, entry_tf: Timeframe, entry_array_id: Optional[str]) -> str:
    """The setup's id: the same instrument, entry timeframe and entry array
    (SetupGradeDetail.entry_array_id) always give the same id."""
    if entry_array_id is None:
        # Every array-less setup would otherwise share one id.
        raise ValueError(f"{instrument} {entry_tf.value}: a setup id needs an entry array")
    return deterministic_id("setup", instrument, entry_tf.value, entry_array_id)


def build_order_intent(
    liquidity_map: LiquidityMap,
    view: Mapping[Timeframe, Sequence[Candle]],
    instrument: str,
    as_of: datetime,
    cfg: StrategyConfig,
    typical_spread: Optional[float] = None,
) -> OrderIntent | NoTrade:
    """Turn the engine's graded setup at ``as_of`` into an order, or say why not.

    ``view`` is the candle window the engine analysed: the entry timeframe's
    last close is the current price, and the D1/W1 bars give the daily and
    weekly opens. ``typical_spread`` is the instrument's (InstrumentSpec.
    default_spread); cfg.min_stop_spreads needs it.
    """
    if cfg.min_stop_spreads > 0 and typical_spread is None:
        # Raised, not skipped: a run without spreads must not quietly drop the rule.
        raise ValueError(f"{instrument}: min_stop_spreads {cfg.min_stop_spreads} needs the typical spread")
    setup_grade = liquidity_map.setup_grade
    if setup_grade is None:
        return NoTrade(instrument, as_of, "NO_TRADE", "NO_GRADE", "no grade computed")
    if setup_grade.grade == SetupGrade.NO_TRADE:
        return NoTrade(instrument, as_of, "NO_TRADE", "NO_TRADE", setup_grade.grade_reason)

    # A tradeable grade always has a setup sequence: the grader gates on it
    # (liquidity-engine Req 18.9), and its array is the entry array.
    sequence = liquidity_map.setup_sequence
    if sequence is None:
        raise ValueError(f"{instrument}: graded {setup_grade.grade.value} without a setup sequence")

    # The direction is the sequence's (Req 19.2), not the D1 bias: a
    # counter-trend setup trades against it, capped at B. (It was inferred
    # from the stop's side of the entry.)
    direction: Direction = "LONG" if sequence.direction == BiasDirection.BULLISH else "SHORT"
    refused = _candle_policy(liquidity_map, sequence, cfg)
    if refused is not None:
        return NoTrade(instrument, as_of, setup_grade.grade.value, *refused)

    entry = setup_grade.suggested_entry
    stop_loss = (setup_grade.suggested_stop if cfg.stop_mode == StopMode.WICK
                 else setup_grade.protected_swing_body_stop)
    stop_beyond_entry = stop_loss is not None and (stop_loss < entry if direction == "LONG" else stop_loss > entry)
    if not stop_beyond_entry:
        return NoTrade(
            instrument, as_of, setup_grade.grade.value, "INVALID_STOP",
            f"{cfg.stop_mode.value} stop {stop_loss} is not beyond the {direction} entry {entry}",
        )

    risk = abs(entry - stop_loss)
    if cfg.min_stop_spreads > 0 and risk < cfg.min_stop_spreads * typical_spread:
        return NoTrade(
            instrument, as_of, setup_grade.grade.value, "STOP_TOO_TIGHT",
            f"{cfg.stop_mode.value} stop {risk:.6g} away is under {cfg.min_stop_spreads} x the "
            f"{typical_spread:.6g} typical spread",
        )

    take_profit_1, take_profit_2 = _pick_targets(liquidity_map, entry, direction, cfg)
    r_ratio = abs(take_profit_1 - entry) / risk

    if r_ratio < cfg.min_rr:
        return NoTrade(
            instrument, as_of, setup_grade.grade.value, "RR_BELOW_MIN",
            f"R:R {r_ratio:.2f} is below the {cfg.min_rr} floor", r_ratio,
        )

    time_features = TimeWindowClassifier().classify(
        as_of,
        instrument,
        current_price=view[cfg.entry_tf][-1].close,
        daily_open=view[Timeframe.D1][-1].open,
        weekly_open=view[Timeframe.W1][-1].open,
    )
    d1_bias = liquidity_map.htf_bias[Timeframe.D1.value]

    return OrderIntent(
        setup_id=setup_id_for(instrument, cfg.entry_tf, setup_grade.entry_array_id),
        instrument=instrument,
        entry_tf=cfg.entry_tf,
        as_of=as_of,
        grade=setup_grade.grade,
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        r_ratio=r_ratio,
        confidence=cfg.grade_confidence[setup_grade.grade],
        time_features=time_features,
        patterns=tuple(_build_patterns(liquidity_map)),
        regime=f"TRENDING_{d1_bias.direction.value}",
    )


def _candle_policy(
    liquidity_map: LiquidityMap, sequence: SetupSequence, cfg: StrategyConfig,
) -> Optional[tuple[NoTradeReason, str]]:
    """The first candle anticipation rule the setup fails, as (reason, detail);
    None when it passes them all (liquidity-engine Req 23.1-23.4)."""
    profile = liquidity_map.candle_profile
    bullish = sequence.direction == BiasDirection.BULLISH
    wick = sequence.protected_swing.wick
    if cfg.bias_mode == BiasMode.PROFILE:
        if profile is None or profile.direction == BiasDirection.NEUTRAL:
            return "NO_ANTICIPATION", "no anticipated direction for the candle"
        if profile.direction != sequence.direction:
            return "AGAINST_PROFILE", (f"{sequence.direction.value} setup in a candle anticipated "
                                       f"{profile.direction.value}")
    if cfg.require_false_move:
        if profile is None or not (wick < profile.frame_open if bullish else wick > profile.frame_open):
            side = "below" if bullish else "above"
            open_ = "no candle open" if profile is None else f"the open {profile.frame_open}"
            return "NO_FALSE_MOVE", f"protected swing {wick} is not {side} {open_}"
    if cfg.time_window == TimeWindow.MANIPULATION and (profile is None or not profile.raid_in_window):
        return "OUTSIDE_WINDOW", (f"raid at {sequence.raid.raided_at:%Y-%m-%d %H:%M} UTC is outside the "
                                  f"candle's 01:00-13:00 New York window")
    if cfg.require_htf_poi and not any(
        a.timeframe in _POI_TIMEFRAMES and not a.is_filled and a.direction == sequence.direction
        and a.low <= wick <= a.high
        for a in liquidity_map.pd_arrays
    ):
        return "NO_POI", f"protected swing {wick} is not inside an unfilled H4 or D1 {sequence.direction.value} PD array"
    return None


def _pick_targets(
    liquidity_map: LiquidityMap, entry: float, direction: Direction, cfg: StrategyConfig,
) -> tuple[float, Optional[float]]:
    """The SD targets; under NEAREST, TP1 is the nearer of SD's TP1 and the candle
    profile's draw when the draw lies beyond the entry, and TP2 the other (Req 23.5)."""
    tp1, tp2 = _pick_sd_targets(liquidity_map, entry, direction, cfg.tp_levels)
    profile = liquidity_map.candle_profile
    if cfg.target_mode != TargetMode.NEAREST or profile is None or profile.draw is None:
        return tp1, tp2
    draw = profile.draw.price
    if not (draw > entry if direction == "LONG" else draw < entry):
        return tp1, tp2
    return (draw, tp1) if abs(draw - entry) < abs(tp1 - entry) else (tp1, draw)


def _pick_sd_targets(
    liquidity_map: LiquidityMap, entry: float, direction: Direction, tp_levels: tuple[float, ...],
) -> tuple[float, Optional[float]]:
    """Standard Deviation projection targets replace the earlier crude
    draw_on_liquidity.price stand-in used for take_profit_1.

    The projection is anchored on the setup leg in the sequence's direction
    (liquidity-engine Req 18.15), so TP1 lands beyond the entry by
    construction. Falls back to draw_on_liquidity.price (TP2 left unset)
    when sd_projection is unavailable or its TP1 would still land on the
    wrong side of the entry.
    """
    sd = liquidity_map.sd_projection
    if sd is not None:
        tp1 = sd.targets.get(tp_levels[0])
        tp2 = sd.targets.get(tp_levels[1]) if len(tp_levels) > 1 else None
        lands_correctly = tp1 is not None and (
            (direction == "LONG" and tp1 > entry) or (direction == "SHORT" and tp1 < entry)
        )
        if lands_correctly:
            return tp1, tp2
    return liquidity_map.draw_on_liquidity.price, None


def _build_patterns(liquidity_map: LiquidityMap) -> list[dict]:
    patterns = []
    if liquidity_map.unicorn is not None:
        patterns.append({"type": "UNICORN", "confidence": 0.85})
    if liquidity_map.sweep_detected:
        patterns.append({"type": "LIQUIDITY_SWEEP", "confidence": 0.75})
    if liquidity_map.cisd_cascade is not None and liquidity_map.cisd_cascade.cascade_valid:
        patterns.append({"type": "CISD_CASCADE", "confidence": 0.75})
    return patterns
