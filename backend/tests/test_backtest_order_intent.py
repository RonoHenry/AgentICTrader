"""
Tests for agent/order_intent.py — the order the live runner and the
backtester derive from a graded setup.

Tasks 189 (deterministic setup_id) and 190 (build_order_intent, moved out
of scripts/run_live_agent.py) in .kiro/specs/algo-backtester/tasks.md.
Validates: Requirements 1.2, 1.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.order_intent import NoTrade, OrderIntent, build_order_intent, setup_id_for
from agent.strategy_config import StrategyConfig
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    SDProjection,
    SetupGrade,
    SetupGradeDetail,
    Timeframe,
)
from tests.test_liquidity_engine_perf import FIXTURES, _load
from tests.test_liquidity_grader import full_liquidity_map, make_level

GOLDEN_MESSAGE = Path(__file__).parent / "fixtures" / "backtester" / "order_intent" / "EURUSD_M5_message.json"
AS_OF = datetime(2026, 1, 14, 14, 0, tzinfo=timezone.utc)  # 09:00 New York: NY AM killzone


def test_setup_id_stable_for_same_array_across_consecutive_bars():
    # A real window the live runner graded A (MT5 EURUSD, M5 entries). One
    # and two bars earlier the engine selects the same entry array, so the
    # setup must keep its id: D6 allows one attempt per setup_id, and a
    # fresh id every bar would let it re-enter after a stop-out.
    record, candles_by_tf, t = _load(FIXTURES / "EURUSD_M5.json.gz")
    entry_tf = Timeframe(record["entry_tf"])
    bar = candles_by_tf[entry_tf][-1].timestamp - candles_by_tf[entry_tf][-2].timestamp

    ids = []
    for bars_back in (2, 1, 0):
        window = {
            tf: candles[: len(candles) - bars_back] if tf == entry_tf else candles
            for tf, candles in candles_by_tf.items()
        }
        grade = LiquidityMappingEngine().analyze(window, record["instrument"], t - bars_back * bar).setup_grade
        assert grade.entry_array_id is not None
        ids.append(setup_id_for(record["instrument"], entry_tf, grade.entry_array_id))

    assert len(set(ids)) == 1


def test_setup_id_differs_for_different_arrays_or_entry_tf():
    base = setup_id_for("EURUSD", Timeframe.M5, "array-1")

    assert setup_id_for("EURUSD", Timeframe.M5, "array-1") == base
    assert setup_id_for("EURUSD", Timeframe.M5, "array-2") != base
    assert setup_id_for("EURUSD", Timeframe.M15, "array-1") != base
    assert setup_id_for("GBPUSD", Timeframe.M5, "array-1") != base


def test_setup_id_requires_an_entry_array():
    # Without an array every array-less setup would share one id, and D6
    # would then block all of them after the first attempt.
    with pytest.raises(ValueError, match="entry array"):
        setup_id_for("EURUSD", Timeframe.M5, None)


# ── build_order_intent (task 190) ──────────────────────────────────────────

def _grade(grade=SetupGrade.A, entry=1.1000, stop=1.0990, array_id="m5-fvg") -> SetupGradeDetail:
    return SetupGradeDetail(
        grade=grade, conditions_met=7,
        htf_bias_confirmed=True, draw_on_liquidity_identified=True, liquidity_sweep_confirmed=True,
        displacement_present=True, cisd_confirmed=True, entry_pd_array_present=True,
        stop_placement_valid=True, time_window_aligned=False,
        grade_reason="test grade", suggested_entry=entry, suggested_stop=stop,
        entry_array_high=max(entry, stop), entry_array_low=min(entry, stop),
        entry_array_direction=BiasDirection.BULLISH if stop < entry else BiasDirection.BEARISH,
        entry_array_id=array_id,
    )


def _map(grade: SetupGradeDetail | None, draw: float = 1.1050, sd: SDProjection | None = None):
    return full_liquidity_map(
        instrument="EURUSD", setup_grade=grade, draw_on_liquidity=make_level(price=draw), sd_projection=sd,
    )


def _view(price: float = 1.1000) -> dict[Timeframe, list[Candle]]:
    def bar(tf, ts, o):
        return Candle(timestamp=ts, open=o, high=max(o, price), low=min(o, price), close=price, volume=1,
                      timeframe=tf, instrument="EURUSD")
    return {
        Timeframe.W1: [bar(Timeframe.W1, datetime(2026, 1, 11, 22, tzinfo=timezone.utc), 1.0950)],
        Timeframe.D1: [bar(Timeframe.D1, datetime(2026, 1, 13, 22, tzinfo=timezone.utc), 1.1020)],
        Timeframe.M5: [bar(Timeframe.M5, AS_OF - timedelta(minutes=5), price)],
    }


CFG = StrategyConfig(entry_tf=Timeframe.M5)


def test_no_grade_returns_no_trade_no_grade():
    result = build_order_intent(_map(None), _view(), "EURUSD", AS_OF, CFG)
    assert result == NoTrade(instrument="EURUSD", as_of=AS_OF, grade="NO_TRADE", reason="NO_GRADE",
                             detail="no grade computed")


def test_no_trade_grade_returns_no_trade():
    grade = _grade(SetupGrade.NO_TRADE).model_copy(update={"grade_reason": "only 5/8 conditions"})
    result = build_order_intent(_map(grade), _view(), "EURUSD", AS_OF, CFG)
    assert result == NoTrade(instrument="EURUSD", as_of=AS_OF, grade="NO_TRADE", reason="NO_TRADE",
                             detail="only 5/8 conditions")


def test_rr_below_min_returns_rr_below_min():
    # Risk 10 pips, draw on liquidity 20 pips away: 2R, under the 3R floor.
    lm = _map(_grade(entry=1.1000, stop=1.0990), draw=1.1020)
    result = build_order_intent(lm, _view(), "EURUSD", AS_OF, CFG)
    assert isinstance(result, NoTrade)
    assert (result.grade, result.reason) == ("A", "RR_BELOW_MIN")
    assert result.r_ratio == pytest.approx(2.0)

    # The same setup clears a lower floor. (Not 2.0: float prices make this
    # "2R" 1.9999999999998, and the floor compares unrounded, as live always has.)
    lower = StrategyConfig(entry_tf=Timeframe.M5, min_rr=1.5)
    assert isinstance(build_order_intent(lm, _view(), "EURUSD", AS_OF, lower), OrderIntent)


def test_direction_from_stop_vs_entry():
    # D1 bias is BULLISH in full_liquidity_map; the stop's side decides anyway.
    long = build_order_intent(_map(_grade(entry=1.1000, stop=1.0990), draw=1.1050), _view(), "EURUSD", AS_OF, CFG)
    short = build_order_intent(_map(_grade(entry=1.1000, stop=1.1010), draw=1.0950), _view(), "EURUSD", AS_OF, CFG)
    assert (long.direction, short.direction) == ("LONG", "SHORT")
    assert long.regime == short.regime == "TRENDING_BULLISH"


def test_sd_target_used_when_on_correct_side_else_draw_on_liquidity():
    grade = _grade(entry=1.1000, stop=1.0990)
    above = SDProjection(anchor_0=1.1010, anchor_1=1.0980, targets={2.5: 1.1085, 4.0: 1.1130})
    below = SDProjection(anchor_0=1.0980, anchor_1=1.1010, targets={2.5: 1.0905, 4.0: 1.0860})

    with_sd = build_order_intent(_map(grade, draw=1.1050, sd=above), _view(), "EURUSD", AS_OF, CFG)
    assert (with_sd.take_profit_1, with_sd.take_profit_2) == (1.1085, 1.1130)

    # A LONG can't target below entry: fall back to the draw on liquidity, no TP2.
    wrong_side = build_order_intent(_map(grade, draw=1.1050, sd=below), _view(), "EURUSD", AS_OF, CFG)
    assert (wrong_side.take_profit_1, wrong_side.take_profit_2) == (1.1050, None)

    no_sd = build_order_intent(_map(grade, draw=1.1050), _view(), "EURUSD", AS_OF, CFG)
    assert (no_sd.take_profit_1, no_sd.take_profit_2) == (1.1050, None)

    # The SD levels come from the config.
    tp4_only = StrategyConfig(entry_tf=Timeframe.M5, tp_levels=(4.0,))
    tp4 = build_order_intent(_map(grade, draw=1.1050, sd=above), _view(), "EURUSD", AS_OF, tp4_only)
    assert (tp4.take_profit_1, tp4.take_profit_2) == (1.1130, None)


@pytest.mark.parametrize("grade, confidence", [(SetupGrade.A_PLUS, 0.90), (SetupGrade.A, 0.80), (SetupGrade.B, 0.70)])
def test_confidence_from_grade_mapping(grade, confidence):
    lm = _map(_grade(grade), draw=1.1050)
    assert build_order_intent(lm, _view(), "EURUSD", AS_OF, CFG).confidence == confidence

    custom = StrategyConfig(entry_tf=Timeframe.M5, grade_confidence={"A+": 0.6, "A": 0.5, "B": 0.4})
    assert build_order_intent(lm, _view(), "EURUSD", AS_OF, custom).confidence == custom.grade_confidence[grade]


def _fixture_intent():
    record, candles_by_tf, t = _load(FIXTURES / "EURUSD_M5.json.gz")
    lm = LiquidityMappingEngine().analyze(candles_by_tf, record["instrument"], t)
    cfg = StrategyConfig(entry_tf=Timeframe(record["entry_tf"]))
    return lm, candles_by_tf, t, cfg, build_order_intent(lm, candles_by_tf, record["instrument"], t, cfg)


def _freeze_runner_clock(monkeypatch, runner, t):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return t

    monkeypatch.setattr(runner, "datetime", FrozenDatetime)


def test_to_message_matches_runner_message_minus_candles():
    # The golden is what the runner itself built on this window before the
    # move (see its "source"). Only setup_id differs, by design (task 189).
    lm, _, t, cfg, intent = _fixture_intent()
    golden = json.loads(GOLDEN_MESSAGE.read_text(encoding="utf-8"))["message"]

    message = intent.to_message("AUTONOMOUS")

    assert message.pop("setup_id") == setup_id_for("EURUSD", cfg.entry_tf, lm.setup_grade.entry_array_id)
    assert "candles_by_tf" not in message
    assert json.loads(json.dumps(message)) == golden


def test_runner_delegates_to_build_order_intent(monkeypatch):
    import scripts.run_live_agent as runner

    lm, candles_by_tf, t, cfg, expected = _fixture_intent()
    calls, messages = [], []

    def spy(*args):
        calls.append(args)
        return build_order_intent(*args)

    monkeypatch.setattr(runner, "build_order_intent", spy)
    _freeze_runner_clock(monkeypatch, runner, t)
    graph = SimpleNamespace(run=lambda message: messages.append(message) or SimpleNamespace(
        decision=None, decision_reason="", error=None, trade_id="t-1"))

    summary = runner._process_instrument("EURUSD", lambda tf: candles_by_tf[tf], graph, cfg, "AUTONOMOUS", verbose=False)

    [(_, view, instrument, as_of, used_cfg)] = calls
    assert (view, instrument, as_of, used_cfg) == (candles_by_tf, "EURUSD", t, cfg)
    [message] = messages
    # The runner adds the candle window, so observe_node can run its AI layers.
    assert message == {**expected.to_message("AUTONOMOUS"), "candles_by_tf": runner._serialize_candles_by_tf(candles_by_tf)}
    assert summary == {"instrument": "EURUSD", "grade": "A", "decision": None, "trade_id": "t-1"}


@pytest.mark.parametrize("min_rr, decision", [(3.0, None), (6.0, "SKIP (R:R 5.00 < 6.0)")])
def test_runner_summary_unchanged(monkeypatch, min_rr, decision):
    import scripts.run_live_agent as runner

    _, candles_by_tf, t = _load(FIXTURES / "EURUSD_M5.json.gz")
    _freeze_runner_clock(monkeypatch, runner, t)
    graph = SimpleNamespace(run=lambda message: SimpleNamespace(decision=None, decision_reason="", error=None, trade_id=None))
    cfg = StrategyConfig(entry_tf=Timeframe.M5, min_rr=min_rr)

    summary = runner._process_instrument("EURUSD", lambda tf: candles_by_tf[tf], graph, cfg, "AUTONOMOUS", verbose=False)

    assert summary == {"instrument": "EURUSD", "grade": "A", "decision": decision, "trade_id": None}
