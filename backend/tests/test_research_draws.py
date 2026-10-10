"""
Tests for the engine's draws as levels (update 2026-10e): their taken-at
features, their forward labels, ``anchor`` with ``level = "draw"`` and a fixed
direction, and ``stratified`` over the draws.

Task 269 (.kiro/specs/algo-research/tasks.md). A hand-made Monday (2026-01-05)
at 1.1000 with the engine's draws at 1.1050 above and 1.0950 below.
Validates: Requirement 18 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algo_research.events import EventError, run_event
from algo_research.features.market import market_features
from algo_research.hypothesis import HypothesisError, parse_hypothesis
from tests.research_fixtures import Path, grid_for, ny

ABOVE, BELOW = 1.1050, 1.0950


def draw_path() -> Path:
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17), base=1.1000)
    path.bar(ny(2026, 1, 5, 2, 0), h=ABOVE)                # trades up to the draw above: not beyond it
    path.bar(ny(2026, 1, 5, 3, 0), h=1.1060)               # beyond the draw above
    path.bar(ny(2026, 1, 5, 6, 0), lo=1.0940)              # beyond the draw below
    return path


def with_draws(features: pd.DataFrame, known_from=ny(2026, 1, 4, 17, 15)) -> pd.DataFrame:
    """The anticipation as join_anticipation leaves it: known from its first M15 close on."""
    out = features.copy()
    known = (out["t"] >= pd.Timestamp(known_from)).to_numpy()
    out["ant_draw_above_price"] = np.where(known, ABOVE, np.nan)
    out["ant_draw_below_price"] = np.where(known, BELOW, np.nan)
    out["ant_direction"] = np.where(known, "BULLISH", None).astype(object)
    return out


def day(path: Path = None, known_from=ny(2026, 1, 4, 17, 15)):
    frame = (path or draw_path()).frame()
    return frame, with_draws(market_features(frame, grid_for(frame, date(2026, 1, 5), date(2026, 1, 6))), known_from)


def row_at(features: pd.DataFrame, when) -> int:
    return features.index[features["t"] == pd.Timestamp(when)][0]


def with_taken(frame, features: pd.DataFrame) -> pd.DataFrame:
    from algo_research.features.draws import draw_taken_at

    return pd.concat([features, draw_taken_at(frame, features)], axis=1)


# ── taken-at features (Req 18.1) ────────────────────────────────────────────

def test_draw_taken_at_first_m1_beyond_the_draw():
    from algo_research.features.draws import DRAW_COLUMNS, draw_taken_at

    frame, f = day()
    taken = draw_taken_at(frame, f)
    assert list(taken.columns) == list(DRAW_COLUMNS) and taken.index.equals(f.index)
    above, below = taken["ant_draw_above_taken_at"], taken["ant_draw_below_taken_at"]
    assert pd.isna(above[row_at(f, ny(2026, 1, 5, 2, 15))])             # at the draw is not beyond it
    assert pd.isna(above[row_at(f, ny(2026, 1, 5, 3, 0))])              # the 03:00 bar hasn't closed at 03:00
    assert above[row_at(f, ny(2026, 1, 5, 3, 15))] == pd.Timestamp(ny(2026, 1, 5, 3, 1))
    assert above[row_at(f, ny(2026, 1, 5, 16, 45))] == pd.Timestamp(ny(2026, 1, 5, 3, 1))   # stays known
    assert pd.isna(below[row_at(f, ny(2026, 1, 5, 6, 0))])
    assert below[row_at(f, ny(2026, 1, 5, 6, 15))] == pd.Timestamp(ny(2026, 1, 5, 6, 1))


def test_draw_taken_at_null_while_the_draw_is_unknown():
    from algo_research.features.draws import draw_taken_at

    path = draw_path().bar(ny(2026, 1, 4, 17, 20), h=1.1060)            # beyond, before the draw is known
    frame, f = day(path, known_from=ny(2026, 1, 4, 18, 0))
    above = draw_taken_at(frame, f)["ant_draw_above_taken_at"]
    assert pd.isna(above[row_at(f, ny(2026, 1, 4, 17, 45))])
    assert above[row_at(f, ny(2026, 1, 4, 18, 0))] == pd.Timestamp(ny(2026, 1, 4, 17, 21))


def test_draw_taken_at_uses_only_the_past():
    # Property 1 for the new columns: the value at t is the same from data cut off at t.
    from algo_research.features.draws import DRAW_COLUMNS, draw_taken_at
    from tests.test_research_features import _truncated

    frame, f = day()
    full = draw_taken_at(frame, f)
    for i in range(0, len(f), 5):
        t = f["t"].iloc[i]
        again = draw_taken_at(_truncated(frame, t.to_pydatetime()), f[f["t"] <= t])
        for name in DRAW_COLUMNS:
            a, b = full[name].iloc[i], again.loc[f.index[i], name]
            assert (pd.isna(a) and pd.isna(b)) or a == b, (t, name, a, b)


# ── forward labels (Req 18.2) ───────────────────────────────────────────────

def test_draw_labels_hit_after_t_and_before_the_close():
    from algo_research.labels import DRAW_LABELS, LABEL_COLUMNS, draw_labels

    frame, f = day()
    labels = draw_labels(frame, f)
    assert list(labels.columns) == list(DRAW_LABELS) and set(DRAW_LABELS) <= set(LABEL_COLUMNS)
    at_3 = row_at(f, ny(2026, 1, 5, 3, 0))                              # the 03:00 bar opens at t: it counts
    assert bool(labels.at[at_3, "ant_draw_above_hit_after"])
    assert labels.at[at_3, "ant_draw_above_hit_at"] == pd.Timestamp(ny(2026, 1, 5, 3, 1))
    after = row_at(f, ny(2026, 1, 5, 3, 15))
    assert not bool(labels.at[after, "ant_draw_above_hit_after"]) and pd.isna(labels.at[after, "ant_draw_above_hit_at"])
    assert bool(labels.at[after, "ant_draw_below_hit_after"])           # the 06:00 bar is still to come
    _, late = day(known_from=ny(2026, 1, 4, 18, 0))
    early = draw_labels(frame, late)["ant_draw_above_hit_after"]
    assert pd.isna(early[row_at(late, ny(2026, 1, 4, 17, 45))])         # unknown draw: no label


def test_draw_labels_use_only_the_future():
    # Property 2 for the new labels: bars that closed by t can change without changing them.
    from algo_research.labels import DRAW_LABELS, draw_labels
    from tests.test_research_labels import _perturbed

    frame, f = day()
    full = draw_labels(frame, f)
    for i in range(0, len(f), 5):
        t = f["t"].iloc[i]
        again = draw_labels(_perturbed(frame, t, seed=i), f)
        for name in DRAW_LABELS:
            a, b = full[name].iloc[i], again[name].iloc[i]
            assert (pd.isna(a) and pd.isna(b)) or a == b, (t, name, a, b)


# ── anchor with the draws (Req 18.3) ────────────────────────────────────────

def test_anchor_takes_the_draw_on_its_side():
    frame, f = day()
    f = with_taken(frame, f)
    long = run_event(f, "anchor", {"at": "02:00", "direction": "LONG", "level": "draw"})
    assert list(long.rows["direction"]) == ["LONG"]
    assert list(long.rows["level_name"]) == ["ant_draw_above"] and list(long.rows["level"]) == [ABOVE]
    short = run_event(f, "anchor", {"at": "02:00", "direction": "SHORT", "level": "draw"})
    assert list(short.rows["level_name"]) == ["ant_draw_below"] and list(short.rows["level"]) == [BELOW]
    biased = run_event(f, "anchor", {"at": "02:00", "direction_from": "ant_direction", "level": "draw"})
    assert list(biased.rows["direction"]) == ["LONG"] and list(biased.rows["level"]) == [ABOVE]
    late = run_event(f, "anchor", {"at": "04:00", "direction": "LONG", "level": "draw"})   # taken at 03:01
    assert late.rows.empty and late.skipped == {"taken": 1}
    frame, unknown = day(known_from=ny(2026, 1, 4, 18, 0))
    early = run_event(with_taken(frame, unknown), "anchor", {"at": "17:45", "direction": "LONG", "level": "draw"})
    assert early.rows.empty and early.skipped == {"no_level": 1}


def test_anchor_fixed_direction():
    frame, f = day()
    rows = run_event(f, "anchor", {"at": "09:00", "direction": "SHORT"}).rows
    assert list(rows["direction"]) == ["SHORT"]


def test_anchor_direction_and_level_validated():
    frame, f = day()
    with pytest.raises(EventError, match="direction"):
        run_event(f, "anchor", {"at": "09:00", "direction": "LONG", "direction_from": "ant_direction"})
    with pytest.raises(EventError, match="direction"):
        run_event(f, "anchor", {"at": "09:00", "level": "draw"})          # a draw needs a side
    with pytest.raises(EventError):
        run_event(f, "anchor", {"at": "09:00", "direction": "UP"})
    with pytest.raises(EventError):
        run_event(f, "anchor", {"at": "09:00", "direction": "LONG", "level": "pdh"})


# ── stratified over the draws (Req 18.4) ────────────────────────────────────

def test_stratified_pools_both_engine_draws():
    from algo_research.baselines import stratified

    rng = np.random.default_rng(5)
    n = 3000
    up, down = rng.uniform(0, 2, n), rng.uniform(0, 2, n)               # distances in ATR
    hour = rng.choice([9, 10], n)
    features = pd.DataFrame({"close": 1.0, "atr_d1": 0.01, "ny_minute": hour * 60,
                             "ant_draw_above_price": 1.0 + up * 0.01, "ant_draw_below_price": 1.0 - down * 0.01,
                             "ant_draw_above_taken_at": pd.NaT, "ant_draw_below_taken_at": pd.NaT})
    features["ant_draw_above_taken_at"] = pd.Series(pd.NaT, index=features.index, dtype="datetime64[ns, UTC]")
    features.loc[7, "ant_draw_above_taken_at"] = pd.Timestamp("2026-01-05 08:00", tz="UTC")   # taken: not pooled
    hit_up = rng.random(n) < 0.8 * np.exp(-up)
    hit_down = rng.random(n) < 0.5 * np.exp(-down)
    labels = pd.DataFrame({"ant_draw_above_hit_after": pd.array(hit_up, dtype="boolean"),
                           "ant_draw_below_hit_after": pd.array(hit_down, dtype="boolean")})
    events = pd.DataFrame({"row": [10, 11], "level_name": ["ant_draw_above", "ant_draw_below"],
                           "level": [features.at[10, "ant_draw_above_price"], features.at[11, "ant_draw_below_price"]]})
    sums, counts = stratified(features, labels, events, candidates=("ant_draw_above", "ant_draw_below"))
    keep = np.arange(n) != 7
    distance = np.concatenate([up[keep], down])
    hits = np.concatenate([hit_up[keep], hit_down]).astype(float)
    hours = np.concatenate([hour[keep], hour])
    edges = np.quantile(distance, np.linspace(0, 1, 11))
    decile = np.clip(np.searchsorted(edges, distance, "right") - 1, 0, 9)
    for i, d in enumerate((up[10], down[11])):
        mine = np.clip(np.searchsorted(edges, d, "right") - 1, 0, 9)
        cell = (decile == mine) & (hours == hour[10 + i])
        assert counts[i] == 1 and sums[i] == pytest.approx(hits[cell].mean())


# ── the schema ──────────────────────────────────────────────────────────────

H001 = '''
id = "H001"
title = "The engine's bias picks the side whose draw gets delivered"
statement = "On bullish-bias days the draw above is reached more often than a draw at the same distance."
family = "bias"
created = 2026-10-10

[event]
name = "anchor"
params = { at = "17:15", direction = "LONG", level = "draw" }
where = "ant_direction == 'BULLISH'"

[measure]
kind = "rate"
of = "level_hit_after"

[baselines]
use = ["stratified"]

[pass]
require = [{ stat = "rate", versus = "stratified" }]
'''


def test_schema_accepts_draw_rates_with_stratified():
    h = parse_hypothesis(H001)
    assert h.event.params["level"] == "draw" and h.baselines.use == ("stratified",)
    with pytest.raises(HypothesisError, match="direction"):
        parse_hypothesis(H001.replace('direction = "LONG"', 'direction = "LONG", direction_from = "ant_direction"'))
    with pytest.raises(HypothesisError, match="stratified"):
        parse_hypothesis(H001.replace(', level = "draw"', ""))         # no level: nothing to stratify by
    assert parse_hypothesis(H001.replace('of = "level_hit_after"', 'of = "ant_draw_above_hit_after"'))


def test_anchor_at_the_open_is_each_candles_first_known_close():
    # Gold pauses after 17:00 New York, so "the bias as known at the open" can't be a fixed 17:15:
    # at = "open" is each candle's first M15 close with its D1 open known (when the anticipation is).
    frame, f = day()
    rows = run_event(f, "anchor", {"at": "open", "direction": "LONG"}).rows
    assert [t.to_pydatetime() for t in rows["t"]] == [ny(2026, 1, 4, 17, 15)]
    gold = draw_path().drop(ny(2026, 1, 4, 17), ny(2026, 1, 4, 18, 2))      # the daily break
    frame, g = day(gold, known_from=ny(2026, 1, 4, 18, 15))
    rows = run_event(with_taken(frame, g), "anchor", {"at": "open", "direction": "LONG", "level": "draw"}).rows
    assert [t.to_pydatetime() for t in rows["t"]] == [ny(2026, 1, 4, 18, 15)]
    with pytest.raises(EventError):
        run_event(f, "anchor", {"at": "close"})


# ── objective_touch (task 270, Req 19) ──────────────────────────────────────

def touch_day(bars: dict, direction: str = "BULLISH"):
    """A Monday at 1.1000 with the given (time, high, low) overrides, the draws at 1.1050 / 1.0950."""
    path = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17), base=1.1000)
    for when, (h, lo) in bars.items():
        path.bar(when, h=h, lo=lo)
    frame, f = day(path)
    f["ant_direction"] = np.where(f["ant_direction"].notna(), direction, None).astype(object)
    return with_taken(frame, f)


def touch(features, **params):
    return run_event(features, "objective_touch", params).rows


def test_objective_touch_long_from_the_sell_side_draw():
    f = touch_day({ny(2026, 1, 5, 5, 10): (None, 1.0940), ny(2026, 1, 5, 5, 12): (None, 1.0930)})
    rows = touch(f)
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["t"] == pd.Timestamp(ny(2026, 1, 5, 5, 15)) and row["direction"] == "LONG"
    assert row["objective"] == BELOW and row["draw_opposite"] == ABOVE
    assert row["touch_extreme"] == pytest.approx(1.0930)                 # the low since the touch, by t
    assert row["with_bias"] is True


def test_objective_touch_short_mirror_and_against_the_bias():
    rows = touch(touch_day({ny(2026, 1, 5, 8, 20): (1.1060, None)}))
    assert list(rows["direction"]) == ["SHORT"] and rows.iloc[0]["t"] == pd.Timestamp(ny(2026, 1, 5, 8, 30))
    assert rows.iloc[0]["objective"] == ABOVE and rows.iloc[0]["touch_extreme"] == pytest.approx(1.1060)
    assert rows.iloc[0]["with_bias"] is False                            # a SHORT on a bullish-bias day


def test_objective_touch_needs_the_opposite_draw_untaken():
    # Above taken at 03:00, below at 06:00: only the SHORT can fire (at 03:15, the draw below still untaken).
    rows = touch(touch_day({ny(2026, 1, 5, 3, 0): (1.1060, None), ny(2026, 1, 5, 6, 0): (None, 1.0940)}))
    assert list(rows["direction"]) == ["SHORT"] and rows.iloc[0]["t"] == pd.Timestamp(ny(2026, 1, 5, 3, 15))


@pytest.mark.parametrize("touch_at, fires", [
    ((0, 50), False),            # before the window
    ((1, 0), True),              # its first minute
    ((12, 59), True),            # its last minute
    ((13, 0), False),            # the window is [01:00, 13:00)
])
def test_objective_touch_window_edges(touch_at, fires):
    f = touch_day({ny(2026, 1, 5, *touch_at): (None, 1.0940)})
    assert (len(touch(f)) == 1) == fires
    assert len(touch(f, window=["00:00", "14:00"])) == 1


def test_objective_touch_once_per_side_and_null_bias_when_neutral():
    f = touch_day({ny(2026, 1, 5, 5, 10): (None, 1.0940), ny(2026, 1, 5, 9, 40): (None, 1.0935)}, "NEUTRAL")
    rows = touch(f)
    assert len(rows) == 1 and rows.iloc[0]["with_bias"] is None


def test_objective_touch_uses_only_the_past():
    # Property 1 for the event: what it fires by t is the same from data cut off at t.
    from algo_research.features.draws import draw_taken_at
    from tests.test_research_features import _truncated

    f = touch_day({ny(2026, 1, 5, 5, 10): (None, 1.0940), ny(2026, 1, 5, 8, 20): (1.1060, None)})
    full = touch(f)
    frame = Path(ny(2026, 1, 4, 17), ny(2026, 1, 6, 17), base=1.1000) \
        .bar(ny(2026, 1, 5, 5, 10), lo=1.0940).bar(ny(2026, 1, 5, 8, 20), h=1.1060).frame()
    for cut in (ny(2026, 1, 5, 5, 15), ny(2026, 1, 5, 8, 30), ny(2026, 1, 5, 12, 0)):
        short = _truncated(frame, cut)
        g = with_draws(market_features(short, grid_for(short, date(2026, 1, 5), date(2026, 1, 6))))
        g = pd.concat([g, draw_taken_at(short, g)], axis=1)
        again = touch(g)
        want = full[full["t"] <= pd.Timestamp(cut)].reset_index(drop=True)
        assert list(again["t"]) == list(want["t"]) and list(again["direction"]) == list(want["direction"])
        assert list(again["touch_extreme"]) == list(want["touch_extreme"])


def test_objective_touch_registered_with_levels_and_with_bias():
    from algo_research.events import EVENTS

    event = EVENTS["objective_touch"]
    assert event.levels == ("objective", "touch_extreme", "draw_opposite") and event.attributes == ("with_bias",)
    with pytest.raises(EventError):
        touch(touch_day({}), window=["13:00", "01:00"])
