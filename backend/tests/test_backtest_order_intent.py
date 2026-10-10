"""
Tests for agent/order_intent.py — the order the live runner and the
backtester derive from a graded setup.

Tasks 189 (deterministic setup_id) and 190 (build_order_intent, moved out
of scripts/run_live_agent.py) in .kiro/specs/algo-backtester/tasks.md, and
task 231 in .kiro/specs/liquidity-engine/tasks.md (direction, stop mode and
targets from the setup sequence), and task 238 there (the candle
anticipation policy, nearest targets and the minimum stop).
Validates: Requirements 1.2, 1.3 (.kiro/specs/algo-backtester/requirements.md);
Requirements 19, 23, 25.2; Properties 37, 38 (.kiro/specs/liquidity-engine/requirements.md)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent.order_intent import NoTrade, OrderIntent, build_order_intent, setup_id_for
from agent.strategy_config import StopMode, StrategyConfig
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import (
    BiasDirection,
    Candle,
    CandleProfile,
    Objective,
    PDArrayType,
    SDProjection,
    SetupGrade,
    SetupGradeDetail,
    SetupSequence,
    Timeframe,
)
from tests.test_liquidity_engine_perf import FIXTURES, _load
from tests.test_liquidity_grader import full_liquidity_map, make_level, make_pdarray, make_sequence

GOLDEN_MESSAGE = Path(__file__).parent / "fixtures" / "backtester" / "order_intent" / "EURUSD_M5_message.json"
GOLDEN_SOURCE = ("build_order_intent(...).to_message('AUTONOMOUS') on engine_windows/EURUSD_M5.json.gz at its "
                 "timestamp, live default StrategyConfig with entry_tf M5; setup_id and candles_by_tf left out. "
                 "Re-baselined by the setup-sequence grader and order derivation (liquidity-engine tasks 228-231); first captured from "
                 "scripts/run_live_agent.py before task 190 (commit 24fc14a)")
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

def _grade(grade=SetupGrade.A, entry=1.1000, stop=1.0990, array_id="m5-fvg", body=None) -> SetupGradeDetail:
    # The body stop sits between the wick stop and the entry, as the grader places it.
    return SetupGradeDetail(
        grade=grade, conditions_met=7,
        htf_bias_confirmed=True, draw_on_liquidity_identified=True, liquidity_sweep_confirmed=True,
        displacement_present=True, cisd_confirmed=True, entry_pd_array_present=True,
        stop_placement_valid=True, time_window_aligned=False,
        grade_reason="test grade", suggested_entry=entry, suggested_stop=stop,
        entry_array_high=max(entry, stop), entry_array_low=min(entry, stop),
        entry_array_direction=BiasDirection.BULLISH if stop < entry else BiasDirection.BEARISH,
        entry_array_id=array_id,
        protected_swing_body_stop=stop + 0.4 * (entry - stop) if body is None else body,
    )


_FROM_GRADE = object()


def _sequence_for(grade: Optional[SetupGradeDetail]) -> Optional[SetupSequence]:
    """The setup sequence the grader read: on the grade's entry array, in its direction."""
    if grade is None:
        return None
    array = make_pdarray(PDArrayType.FVG, grade.entry_array_direction, grade.entry_array_high,
                         grade.entry_array_low, array_id=grade.entry_array_id)
    return make_sequence(array)


def _map(grade: Optional[SetupGradeDetail], draw: float = 1.1050, sd: Optional[SDProjection] = None,
         sequence=_FROM_GRADE):
    return full_liquidity_map(
        instrument="EURUSD", setup_grade=grade, draw_on_liquidity=make_level(price=draw), sd_projection=sd,
        setup_sequence=_sequence_for(grade) if sequence is _FROM_GRADE else sequence,
    )


def _bearish(grade: SetupGradeDetail) -> SetupSequence:
    return _sequence_for(grade.model_copy(update={"entry_array_direction": BiasDirection.BEARISH}))


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


def test_direction_from_setup_sequence():
    # Requirement 19.2: the sequence's direction, not the stop's side or the D1
    # bias (BULLISH in full_liquidity_map) decides.
    long = build_order_intent(_map(_grade(entry=1.1000, stop=1.0990), draw=1.1050), _view(), "EURUSD", AS_OF, CFG)
    short = build_order_intent(_map(_grade(entry=1.1000, stop=1.1010), draw=1.0950), _view(), "EURUSD", AS_OF, CFG)
    assert (long.direction, short.direction) == ("LONG", "SHORT")
    assert long.regime == short.regime == "TRENDING_BULLISH"

    # A stop below the entry no longer makes it a LONG: the bearish sequence decides, so it's INVALID_STOP.
    flipped = build_order_intent(_map(_grade(entry=1.1000, stop=1.0990), sequence=_bearish(_grade())),
                                 _view(), "EURUSD", AS_OF, CFG)
    assert isinstance(flipped, NoTrade) and flipped.reason == "INVALID_STOP"


def test_tradeable_grade_needs_a_setup_sequence():
    # The grader never grades a setup without one (Requirement 18.9); a map that does is malformed.
    with pytest.raises(ValueError, match="setup sequence"):
        build_order_intent(_map(_grade(), sequence=None), _view(), "EURUSD", AS_OF, CFG)


def test_stop_mode_wick_uses_suggested_stop():
    grade = _grade(entry=1.1000, stop=1.0990, body=1.0994)
    assert CFG.stop_mode is StopMode.WICK
    intent = build_order_intent(_map(grade, draw=1.1050), _view(), "EURUSD", AS_OF, CFG)
    assert (intent.direction, intent.stop_loss) == ("LONG", 1.0990)
    assert intent.r_ratio == pytest.approx(0.0050 / 0.0010)


def test_stop_mode_body_uses_body_stop():
    grade = _grade(entry=1.1000, stop=1.0990, body=1.0994)
    body = StrategyConfig(entry_tf=Timeframe.M5, stop_mode="BODY")
    intent = build_order_intent(_map(grade, draw=1.1050), _view(), "EURUSD", AS_OF, body)
    assert (intent.direction, intent.stop_loss) == ("LONG", 1.0994)
    assert intent.r_ratio == pytest.approx(0.0050 / 0.0006)

    short = _grade(entry=1.1000, stop=1.1010, body=1.1004)
    assert build_order_intent(_map(short, draw=1.0950), _view(), "EURUSD", AS_OF, body).stop_loss == 1.1004


@pytest.mark.parametrize("stop_mode, stop, body", [
    ("WICK", 1.1000, 1.0995),    # the stop on the entry
    ("WICK", 1.1010, 1.1005),    # a LONG with its stop above the entry
    ("BODY", 1.0990, 1.1002),    # the body stop beyond the entry
    ("BODY", 1.0990, None),      # no body stop recorded
])
def test_invalid_stop_is_no_trade(stop_mode, stop, body):
    # Requirement 19.3: the chosen stop must be beyond the entry in the trade direction.
    grade = _grade(entry=1.1000, stop=1.0990).model_copy(
        update={"suggested_stop": stop, "protected_swing_body_stop": body})
    cfg = StrategyConfig(entry_tf=Timeframe.M5, stop_mode=stop_mode)
    result = build_order_intent(_map(grade, draw=1.1050), _view(), "EURUSD", AS_OF, cfg)
    assert isinstance(result, NoTrade)
    assert (result.grade, result.reason, result.r_ratio) == ("A", "INVALID_STOP", None)
    assert stop_mode in result.detail


def test_default_tp_levels():
    # Requirement 19.4: TP1 at 2.0 SD of the setup leg; TP2 (recorded, not traded) at 2.5.
    assert StrategyConfig().tp_levels == (2.0, 2.5)
    sd = SDProjection(anchor_0=1.1010, anchor_1=1.0980, targets={2.0: 1.1070, 2.5: 1.1085, 4.0: 1.1130})
    intent = build_order_intent(_map(_grade(), draw=1.1050, sd=sd), _view(), "EURUSD", AS_OF, CFG)
    assert (intent.take_profit_1, intent.take_profit_2) == (1.1070, 1.1085)


def test_sd_target_used_when_on_correct_side_else_draw_on_liquidity():
    grade = _grade(entry=1.1000, stop=1.0990)
    above = SDProjection(anchor_0=1.1010, anchor_1=1.0980, targets={2.0: 1.1070, 2.5: 1.1085, 4.0: 1.1130})
    below = SDProjection(anchor_0=1.0980, anchor_1=1.1010, targets={2.0: 1.0920, 2.5: 1.0905, 4.0: 1.0860})

    with_sd = build_order_intent(_map(grade, draw=1.1050, sd=above), _view(), "EURUSD", AS_OF, CFG)
    assert (with_sd.take_profit_1, with_sd.take_profit_2) == (1.1070, 1.1085)

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


def test_to_message_matches_runner_message_minus_candles():
    # The golden was what the runner itself built on this window before the
    # move (task 190); only setup_id differed, by design (task 189). A grader
    # change alters it on purpose: rerun with UPDATE_GOLDEN=1 and commit it
    # with that change (its "source" says which). Runner parity itself is
    # test_runner_delegates_to_build_order_intent.
    lm, _, t, cfg, intent = _fixture_intent()

    message = intent.to_message("AUTONOMOUS")

    assert message.pop("setup_id") == setup_id_for("EURUSD", cfg.entry_tf, lm.setup_grade.entry_array_id)
    assert "candles_by_tf" not in message
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN_MESSAGE.write_text(json.dumps({"source": GOLDEN_SOURCE, "message": message}, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
    golden = json.loads(GOLDEN_MESSAGE.read_text(encoding="utf-8"))["message"]
    assert json.loads(json.dumps(message)) == golden


def test_runner_delegates_to_build_order_intent(monkeypatch):
    import scripts.run_live_agent as runner

    lm, candles_by_tf, t, cfg, expected = _fixture_intent()
    calls, messages = [], []

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return build_order_intent(*args, **kwargs)

    monkeypatch.setattr(runner, "build_order_intent", spy)
    graph = SimpleNamespace(run=lambda message: messages.append(message) or SimpleNamespace(
        decision=None, decision_reason="", error=None, trade_id="t-1"))

    summary = runner._process_instrument("EURUSD", candles_by_tf, t, graph, cfg, "AUTONOMOUS", verbose=False,
                                         typical_spread=0.00008)

    [((_, view, instrument, as_of, used_cfg), kwargs)] = calls
    assert (view, instrument, as_of, used_cfg) == (candles_by_tf, "EURUSD", t, cfg)
    assert kwargs == {"typical_spread": 0.00008}           # for the minimum-stop rule (Req 25.2)
    [message] = messages
    # Detected at hand-off, not at the bar close (see task 192's staleness test).
    assert datetime.fromisoformat(message.pop("detected_at")) > t
    expected_message = expected.to_message("AUTONOMOUS")
    del expected_message["detected_at"]
    # The runner adds the candle window, so observe_node can run its AI layers.
    assert message == {**expected_message, "candles_by_tf": runner._serialize_candles_by_tf(candles_by_tf)}
    assert summary == {"instrument": "EURUSD", "grade": "A", "decision": None, "trade_id": "t-1"}


@pytest.mark.parametrize("min_rr, decision", [(3.0, None), (8.0, "SKIP (R:R 5.92 < 8.0)")])
def test_runner_summary_unchanged(min_rr, decision):
    import scripts.run_live_agent as runner

    _, candles_by_tf, t = _load(FIXTURES / "EURUSD_M5.json.gz")
    graph = SimpleNamespace(run=lambda message: SimpleNamespace(decision=None, decision_reason="", error=None, trade_id=None))
    cfg = StrategyConfig(entry_tf=Timeframe.M5, min_rr=min_rr)

    summary = runner._process_instrument("EURUSD", candles_by_tf, t, graph, cfg, "AUTONOMOUS", verbose=False)

    assert summary == {"instrument": "EURUSD", "grade": "A", "decision": decision, "trade_id": None}


# ── candle anticipation policy (liquidity-engine Req 23, 25.2; task 238) ───
# A LONG from 1.1000 with its WICK stop at 1.0990 (10 pips) behind a protected
# swing at 1.0989; a SHORT mirrors it with the swing at 1.1011.

LONG_WICK, SHORT_WICK = 1.0989, 1.1011
BULL, BEAR, NONE = BiasDirection.BULLISH, BiasDirection.BEARISH, BiasDirection.NEUTRAL


def _profile(direction=BULL, frame_open=1.0995, draw: Optional[float] = 1.1030, raid_in_window=True) -> CandleProfile:
    objective = None if draw is None or direction == NONE else Objective(
        kind="POOL", source="PDH" if draw > frame_open else "PDL", timeframe=Timeframe.D1, price=draw,
        direction=BULL if draw > frame_open else BEAR, formed_at=AS_OF - timedelta(days=1))
    return CandleProfile(
        frame_tf=Timeframe.D1, open_time=AS_OF - timedelta(hours=16), frame_open=frame_open, trend=NONE,
        direction=direction, draw=objective, false_move_taken=True, asia_raided=False,
        candle_low=1.0985, candle_low_at=AS_OF - timedelta(hours=3), candle_high=1.1005,
        candle_high_at=AS_OF - timedelta(hours=10), in_window=True, raid_in_window=raid_in_window, weekday=2)


def _policy_map(grade: Optional[SetupGradeDetail] = None, profile: Optional[CandleProfile] = None,
                wick: Optional[float] = None, pd_arrays=None, sd: Optional[SDProjection] = None,
                draw: Optional[float] = None):
    grade = grade or _grade(entry=1.1000, stop=1.0990)
    long = grade.entry_array_direction == BULL
    array = make_pdarray(PDArrayType.FVG, grade.entry_array_direction, grade.entry_array_high,
                         grade.entry_array_low, array_id=grade.entry_array_id)
    sequence = make_sequence(array, wick=wick or (LONG_WICK if long else SHORT_WICK))
    return full_liquidity_map(
        instrument="EURUSD", setup_grade=grade, draw_on_liquidity=make_level(price=draw or (1.1050 if long else 1.0950)),
        sd_projection=sd, setup_sequence=sequence, candle_profile=profile,
        **({} if pd_arrays is None else {"pd_arrays": pd_arrays}))


def policy(**fields) -> StrategyConfig:
    return StrategyConfig(entry_tf=Timeframe.M5, **fields)


def decide(lm, cfg: StrategyConfig, **kwargs):
    return build_order_intent(lm, _view(), "EURUSD", AS_OF, cfg, **kwargs)


def reason(result) -> str:
    return "ORDER" if isinstance(result, OrderIntent) else result.reason


SHORT = _grade(entry=1.1000, stop=1.1010)


def test_profile_mode_needs_an_anticipation():
    cfg = policy(bias_mode="PROFILE")
    for profile in (None, _profile(direction=NONE, draw=None)):
        result = decide(_policy_map(profile=profile), cfg)
        assert isinstance(result, NoTrade) and (result.grade, result.reason) == ("A", "NO_ANTICIPATION")


def test_profile_mode_trades_with_the_anticipated_direction():
    cfg = policy(bias_mode="PROFILE")
    assert reason(decide(_policy_map(profile=_profile()), cfg)) == "ORDER"
    against = _policy_map(profile=_profile(direction=BEAR, draw=1.0950))
    assert reason(decide(against, cfg)) == "AGAINST_PROFILE"
    assert reason(decide(_policy_map(SHORT, profile=_profile(direction=BEAR, frame_open=1.1005, draw=1.0950)), cfg)) == "ORDER"
    assert reason(decide(against, CFG)) == "ORDER"              # OPEN, the default, doesn't read the profile


def test_false_move_needs_the_protected_swing_beyond_the_open():
    cfg = policy(require_false_move=True)
    assert reason(decide(_policy_map(profile=_profile(frame_open=1.0995)), cfg)) == "ORDER"     # 1.0989 below the open
    assert reason(decide(_policy_map(profile=_profile(frame_open=1.0985)), cfg)) == "NO_FALSE_MOVE"
    assert reason(decide(_policy_map(profile=None), cfg)) == "NO_FALSE_MOVE"
    bearish = dict(direction=BEAR, draw=1.0950)
    assert reason(decide(_policy_map(SHORT, profile=_profile(frame_open=1.1005, **bearish)), cfg)) == "ORDER"
    assert reason(decide(_policy_map(SHORT, profile=_profile(frame_open=1.1015, **bearish)), cfg)) == "NO_FALSE_MOVE"


def test_manipulation_window_needs_the_raid_inside_it():
    cfg = policy(time_window="MANIPULATION")
    assert reason(decide(_policy_map(profile=_profile(raid_in_window=True)), cfg)) == "ORDER"
    assert reason(decide(_policy_map(profile=_profile(raid_in_window=False)), cfg)) == "OUTSIDE_WINDOW"
    assert reason(decide(_policy_map(profile=None), cfg)) == "OUTSIDE_WINDOW"
    assert reason(decide(_policy_map(profile=_profile(raid_in_window=False)), CFG)) == "ORDER"     # ANY


def _htf(tf=Timeframe.H4, direction=BULL, low=1.0980, high=1.0995, filled=False):
    return make_pdarray(PDArrayType.FVG, direction, high, low, is_filled=filled, tf=tf)


@pytest.mark.parametrize("arrays, expected", [
    ([_htf()], "ORDER"),                                   # the wick (1.0989) inside an unfilled H4 bullish FVG
    ([_htf(Timeframe.D1)], "ORDER"),
    ([_htf(filled=True)], "NO_POI"),
    ([_htf(direction=BEAR)], "NO_POI"),
    ([_htf(Timeframe.H1)], "NO_POI"),                       # only H4 and D1 arrays are the POI
    ([_htf(Timeframe.W1)], "NO_POI"),
    ([_htf(low=1.0990, high=1.0995)], "NO_POI"),            # the wick is below it
    ([], "NO_POI"),
])
def test_htf_poi_needs_the_wick_inside_an_unfilled_h4_or_d1_array(arrays, expected):
    cfg = policy(require_htf_poi=True)
    assert reason(decide(_policy_map(profile=_profile(), pd_arrays=arrays), cfg)) == expected


def test_policy_checks_in_order_before_the_stop_and_targets():
    cfg = policy(bias_mode="PROFILE", require_false_move=True, time_window="MANIPULATION", require_htf_poi=True)
    steps = [
        (dict(direction=BEAR, frame_open=1.0985, draw=1.0950, raid_in_window=False), [], "AGAINST_PROFILE"),
        (dict(frame_open=1.0985, raid_in_window=False), [], "NO_FALSE_MOVE"),
        (dict(raid_in_window=False), [], "OUTSIDE_WINDOW"),
        (dict(), [], "NO_POI"),
        (dict(), [_htf()], "ORDER"),
    ]
    for fields, arrays, expected in steps:
        assert reason(decide(_policy_map(profile=_profile(**fields), pd_arrays=arrays), cfg)) == expected, expected
    # The policy runs before the stop checks: a LONG with its stop above the entry, against the profile.
    bad_stop = _grade(entry=1.1000, stop=1.0990).model_copy(update={"suggested_stop": 1.1010})
    against = _profile(direction=BEAR, draw=1.0950)
    assert reason(decide(_policy_map(bad_stop, profile=against), policy(bias_mode="PROFILE"))) == "AGAINST_PROFILE"
    assert reason(decide(_policy_map(bad_stop, profile=against), CFG)) == "INVALID_STOP"


SD_ABOVE = SDProjection(anchor_0=1.1010, anchor_1=1.0980, targets={2.0: 1.1070, 2.5: 1.1085})


def test_nearest_target_takes_the_nearer_of_sd_and_the_draw():
    cfg = policy(target_mode="NEAREST")

    def targets(profile, config=cfg):
        intent = decide(_policy_map(profile=profile, sd=SD_ABOVE), config)
        return intent.take_profit_1, intent.take_profit_2

    assert targets(_profile(draw=1.1040)) == (1.1040, 1.1070)          # the draw is nearer: TP1, SD 2.0 is TP2
    assert targets(_profile(draw=1.1100)) == (1.1070, 1.1100)          # SD 2.0 is nearer
    assert targets(_profile(direction=BEAR, draw=1.0950)) == (1.1070, 1.1085)   # a draw behind the entry: SD
    assert targets(None) == (1.1070, 1.1085)
    assert targets(_profile(draw=1.1040), CFG) == (1.1070, 1.1085)     # SD, the default
    # min_rr still applies: a draw 2R away.
    assert reason(decide(_policy_map(profile=_profile(draw=1.1020), sd=SD_ABOVE), cfg)) == "RR_BELOW_MIN"


def test_minimum_stop_in_typical_spreads():
    cfg = policy(min_stop_spreads=2.0)
    lm = _policy_map(profile=_profile())                                # a 10-pip stop
    assert reason(decide(lm, cfg, typical_spread=0.0004)) == "ORDER"    # needs 8 pips
    tight = decide(lm, cfg, typical_spread=0.0006)                     # needs 12 pips
    assert isinstance(tight, NoTrade) and (tight.grade, tight.reason) == ("A", "STOP_TOO_TIGHT")
    assert "2.0" in tight.detail
    with pytest.raises(ValueError, match="spread"):
        decide(lm, cfg)                                                 # the rule can't be skipped silently
    assert reason(decide(lm, CFG)) == "ORDER"                           # off by default: no spread needed
    body = policy(min_stop_spreads=2.0, stop_mode="BODY")               # measured to the chosen stop
    body_grade = _grade(entry=1.1000, stop=1.0990, body=1.0995)
    assert reason(decide(_policy_map(body_grade, profile=_profile()), body, typical_spread=0.0004)) == "STOP_TOO_TIGHT"


@settings(max_examples=150, deadline=None)
@given(long=st.booleans(), direction=st.sampled_from([BULL, BEAR, NONE]), frame_open=st.floats(1.0980, 1.1020),
       draw=st.floats(1.0880, 1.1120), sd_distance=st.floats(0.0005, 0.0150), raid_in_window=st.booleans())
def test_property_37_38_policy_gates_and_nearest_target(long, direction, frame_open, draw, sd_distance,
                                                        raid_in_window):
    """Property 37: an order under these gates goes the profile's way, with its protected wick beyond
    the open on the false-move side and its raid in the window. Property 38: under NEAREST, TP1 lies
    beyond the entry and no further than SD 2.0."""
    grade = _grade(entry=1.1000, stop=1.0990) if long else SHORT
    sd2 = 1.1000 + sd_distance if long else 1.1000 - sd_distance
    sd = SDProjection(anchor_0=1.1010, anchor_1=1.0980, targets={2.0: sd2, 2.5: sd2})
    profile = _profile(direction=direction, frame_open=frame_open, draw=draw, raid_in_window=raid_in_window)
    cfg = policy(bias_mode="PROFILE", require_false_move=True, time_window="MANIPULATION", target_mode="NEAREST",
                 min_rr=0)
    result = decide(_policy_map(grade, profile=profile, sd=sd), cfg)
    if not isinstance(result, OrderIntent):
        return
    wick = LONG_WICK if long else SHORT_WICK
    assert result.direction == ("LONG" if profile.direction == BULL else "SHORT")
    assert (wick < frame_open) if long else (wick > frame_open)
    assert profile.raid_in_window
    tp1 = result.take_profit_1
    assert (tp1 > result.entry) if long else (tp1 < result.entry)
    assert abs(tp1 - result.entry) <= abs(sd2 - result.entry)
