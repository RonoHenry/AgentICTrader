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

Validates: Requirements 1.2, 1.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from agent.strategy_config import StrategyConfig
from liquidity_engine.models import Candle, LiquidityMap, SetupGrade, Timeframe
from liquidity_engine.utils.id_utils import deterministic_id
from ml.features.session_features import TimeFeatures, TimeWindowClassifier

__all__ = ["NoTrade", "OrderIntent", "build_order_intent", "setup_id_for"]

Direction = Literal["LONG", "SHORT"]
NoTradeReason = Literal["NO_GRADE", "NO_TRADE", "RR_BELOW_MIN"]


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
    grade: str             # "NO_TRADE", or the letter grade that fell short of min R:R
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
) -> OrderIntent | NoTrade:
    """Turn the engine's graded setup at ``as_of`` into an order, or say why not.

    ``view`` is the candle window the engine analysed: the entry timeframe's
    last close is the current price, and the D1/W1 bars give the daily and
    weekly opens.
    """
    setup_grade = liquidity_map.setup_grade
    if setup_grade is None:
        return NoTrade(instrument, as_of, "NO_TRADE", "NO_GRADE", "no grade computed")
    if setup_grade.grade == SetupGrade.NO_TRADE:
        return NoTrade(instrument, as_of, "NO_TRADE", "NO_TRADE", setup_grade.grade_reason)

    # A tradeable grade always has an entry array: without one, both the
    # entry-array and stop-placement conditions fail, leaving at most 6/8.
    entry = setup_grade.suggested_entry
    stop_loss = setup_grade.suggested_stop

    # Direction must come from the entry/stop relationship itself, not the
    # overall D1 bias: SetupGrader picks whichever unfilled PD array has the
    # highest strength_score for suggested_entry/suggested_stop, and that
    # array's own polarity (which can be a countertrend micro-structure
    # array) — not the D1 bias — is what _suggested_stop actually places the
    # stop relative to (BEARISH array -> stop above entry; BULLISH -> stop
    # below). Inferring from D1 bias instead caused a stop placed on the
    # wrong side of entry, which MT5 correctly rejected.
    direction: Direction = "LONG" if stop_loss < entry else "SHORT"
    take_profit_1, take_profit_2 = _pick_sd_targets(liquidity_map, entry, direction, cfg.tp_levels)
    r_ratio = abs(take_profit_1 - entry) / abs(entry - stop_loss)

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


def _pick_sd_targets(
    liquidity_map: LiquidityMap, entry: float, direction: Direction, tp_levels: tuple[float, ...],
) -> tuple[float, Optional[float]]:
    """Standard Deviation projection targets replace the earlier crude
    draw_on_liquidity.price stand-in used for take_profit_1.

    Falls back to draw_on_liquidity.price (TP2 left unset) when
    sd_projection is unavailable (no displacement leg found), or when its
    direction — derived from D1 bias inside the engine — disagrees with
    this trade's actual direction (derived from the entry array itself,
    which can differ from D1 bias, see the direction-inference comment
    above) and would land the target on the wrong side of entry.
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
