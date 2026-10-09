"""
Tests for algo_research/hypothesis.py and filters.py — the hypothesis schema,
its parameter list, its hash, and the `where` / label-expression whitelist.

Task 251 (.kiro/specs/algo-research/tasks.md).
Validates: Requirements 6.2, 8.1, 8.5, 9.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algo_research.filters import FilterError, compile_filter
from algo_research.hypothesis import HypothesisError, file_sha256, load_hypothesis, parse_hypothesis

H002 = '''
id = "H002"
title = "A London raid of the Asian range reverses to the range's other side"
statement = """
When price trades through the Asian low between 01:00 and 09:00 New York, and an M15 bar
closes back above it before the Asian high is taken, price reaches the Asian high before it
breaks the raid's low more often than a coin flip and than the same trade at random times,
and the trade is profitable after costs. Mirrored for the Asian high.
"""
family = "po3"
created = 2026-10-10
slice = "confirm"
# supersedes = "H00x"                  # when this replaces a changed question

[event]
name = "asia_raid_reclaim"
params = { window = ["01:00", "09:00"], reclaim_within = 4 }
where = ""                               # e.g. "w1_trend == 'UP'"

[measure]
kind = "race"                            # race | direction | rate | move

[trade]                                  # races only
direction = "event"                      # the event's own direction
stop = { kind = "level", name = "raid_extreme" }
target = { kind = "level", name = "asia_opposite" }   # or { kind = "r", value = 2.0 } / { kind = "atr", value = 0.5 }
time_limit = "day_close"                 # or { minutes = 240 }

[baselines]
use = ["coin_flip", "random_time"]

[pass]
min_events = 100
min_days = 60
require = [
  { stat = "win_rate", versus = "coin_flip" },
  { stat = "win_rate", versus = "random_time" },
  { stat = "mean_net_r" },                # versus nothing: its own lower bound above min_effect
]
'''

H001 = '''
id = "H001"
title = "The engine's daily anticipation calls the rest of the day"
statement = "At 05:00 and at 09:00 New York, the rest of the day moves the anticipated way."
family = "po3"
created = 2026-10-10

[event]
name = "anchor"
params = { at = "05:00", direction_from = "ant_direction" }

[vary]
key = "event.params.at"
values = ["05:00", "09:00"]

[measure]
kind = "direction"

[baselines]
use = ["naive:always_long", "naive:prev_day_dir", "naive:w1_trend", "naive:side_d1_open",
       "naive:side_midnight_open", "random_time"]

[pass]
min_events = 150
min_days = 100
require = [{ stat = "accuracy", versus = "best_naive" }]
'''


def replace(text: str, old: str, new: str) -> str:
    assert old in text, old
    return text.replace(old, new)


def test_design_h002_example_loads():
    h = parse_hypothesis(H002)
    assert (h.id, h.family, h.slice) == ("H002", "po3", "confirm")
    assert h.event.name == "asia_raid_reclaim" and h.event.params == {"window": ["01:00", "09:00"], "reclaim_within": 4}
    assert h.measure.kind == "race" and h.trade.stop.name == "raid_extreme"
    assert h.trade.time_limit == "day_close"
    assert [r.stat for r in h.pass_.require] == ["win_rate", "win_rate", "mean_net_r"]
    assert h.pass_.require[2].versus is None and h.pass_.require[2].min_effect == 0.0
    [test] = h.tests()
    assert test.name == "" and test.hypothesis is h


@pytest.mark.parametrize("old, new, field", [
    ('title = "A London', 'titel = "A London', "title"),                                  # missing field
    ('kind = "race"', 'kind = "races"', "measure.kind"),
    ("reclaim_within = 4", "reclaim_within = 0", "event.params.reclaim_within"),
    ("reclaim_within = 4", "reclaim_within = 4, wndow = 1", "event.params.wndow"),
    ('name = "asia_raid_reclaim"', 'name = "asia_raid"', "event.name"),
    ('id = "H002"', 'id = "H2"', "id"),
    ('name = "raid_extreme"', 'name = "raid_extremes"', "trade.stop.name"),
    ('{ kind = "level", name = "asia_opposite" }', '{ kind = "r" }', "trade.target.value"),
    ('use = ["coin_flip", "random_time"]', 'use = ["coin_flip", "random_tme"]', "baselines.use"),
    ('{ stat = "win_rate", versus = "coin_flip" }', '{ stat = "win_rat", versus = "coin_flip" }', "pass.require"),
    ('{ stat = "win_rate", versus = "coin_flip" }', '{ stat = "win_rate", versus = "stratified" }', "pass.require"),
    ('time_limit = "day_close"', 'time_limit = "week_close"', "trade.time_limit"),
])
def test_each_invalid_field_is_named(old, new, field):
    with pytest.raises(HypothesisError, match=field.replace(".", r"\.")):
        parse_hypothesis(replace(H002, old, new))


def test_race_without_trade_refused_and_trade_only_for_races():
    no_trade = H002[:H002.index("[trade]")] + H002[H002.index("[baselines]"):]
    with pytest.raises(HypothesisError, match="trade"):
        parse_hypothesis(no_trade)
    with pytest.raises(HypothesisError, match="trade"):
        parse_hypothesis(replace(H001, "[measure]", '[trade]\nstop = { kind = "atr", value = 0.5 }\n'
                                 'target = { kind = "r", value = 2.0 }\n\n[measure]'))


def test_baselines_must_fit_the_measure():
    with pytest.raises(HypothesisError, match="naive:always_long"):
        parse_hypothesis(replace(H002, 'use = ["coin_flip", "random_time"]', 'use = ["coin_flip", "naive:always_long"]'))
    with pytest.raises(HypothesisError, match="best_naive"):
        parse_hypothesis(replace(H002, 'versus = "coin_flip" }', 'versus = "best_naive" }'))
    with pytest.raises(HypothesisError, match="naive:sometimes"):
        parse_hypothesis(replace(H001, '"naive:always_long"', '"naive:sometimes"'))


def test_direction_needs_a_directional_event():
    with pytest.raises(HypothesisError, match="direction"):
        parse_hypothesis(replace(H001, ', direction_from = "ant_direction"', ""))


def test_candle_labels_only_with_the_daily_event():
    rate = '''
id = "H004"
title = "Lows of up days form in the 01/05/09 H4 candles"
statement = "On up days the low forms in the 01:00, 05:00 or 09:00 H4 candle more often than shuffled paths."
family = "replication"
created = 2026-10-10

[event]
name = "daily"

[measure]
kind = "rate"
of = "day_low_h4 in [2, 3, 4]"
given = "day_dir == 1"

[baselines]
use = ["shuffled_path"]

[pass]
require = [{ stat = "rate", versus = "shuffled_path" }]
'''
    assert parse_hypothesis(rate).measure.of == "day_low_h4 in [2, 3, 4]"
    leaky = replace(rate, 'name = "daily"', 'name = "anchor"\nparams = { at = "09:00" }')
    leaky = replace(leaky, 'use = ["shuffled_path"]', 'use = ["random_time"]')
    leaky = replace(leaky, 'versus = "shuffled_path"', 'versus = "random_time"')
    with pytest.raises(HypothesisError, match="day_low_h4"):
        parse_hypothesis(leaky)


def test_where_reads_features_only():
    assert parse_hypothesis(replace(H002, 'where = ""', '''where = "w1_trend == 'UP' and in_window"''')).event.where
    with pytest.raises(HypothesisError, match="rem_move.*label"):
        parse_hypothesis(replace(H002, 'where = ""', 'where = "rem_move > 0"'))
    with pytest.raises(HypothesisError, match="no_such_column"):
        parse_hypothesis(replace(H002, 'where = ""', 'where = "no_such_column > 0"'))


def test_level_hit_alias_resolves_per_row():
    h = parse_hypothesis('''
id = "H003"
title = "Trend-side PDH/PDL trades more often than its distance predicts"
statement = "With the W1 trend, the previous day's level on the trend's side trades later that day."
family = "levels"
created = 2026-10-10

[event]
name = "level_open"
params = { level = "trend", at = "09:00" }

[measure]
kind = "rate"
of = "level_hit_after"

[baselines]
use = ["stratified"]

[pass]
require = [{ stat = "rate", versus = "stratified" }]
''')
    assert h.measure.of == "level_hit_after"


def test_a_parameter_list_expands_to_one_test_per_value():
    h = parse_hypothesis(H001)
    tests = h.tests()
    assert [t.name for t in tests] == ["at=05:00", "at=09:00"]
    assert [t.hypothesis.event.params["at"] for t in tests] == ["05:00", "09:00"]
    assert all(t.hypothesis.event.params["direction_from"] == "ant_direction" for t in tests)
    with pytest.raises(HypothesisError, match="vary.key"):
        parse_hypothesis(replace(H001, 'key = "event.params.at"', 'key = "event.params.when"'))
    with pytest.raises(HypothesisError, match="vary.values"):
        parse_hypothesis(replace(H001, 'values = ["05:00", "09:00"]', 'values = ["05:00", "09:07"]'))


def test_the_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "H002-lf.toml", tmp_path / "H002-crlf.toml"
    lf.write_bytes(H002.encode())
    crlf.write_bytes(H002.replace("\n", "\r\n").encode())
    assert file_sha256(lf) == file_sha256(crlf)
    loaded = load_hypothesis(lf)
    assert loaded.sha256 == file_sha256(lf) and loaded.path == lf
    (tmp_path / "H002-edit.toml").write_bytes(H002.replace("min_days = 60", "min_days = 61").encode())
    assert file_sha256(tmp_path / "H002-edit.toml") != file_sha256(lf)


def test_file_name_must_match_the_id(tmp_path):
    path = tmp_path / "H003-wrong.toml"
    path.write_text(H002, encoding="utf-8")
    with pytest.raises(HypothesisError, match="H003"):
        load_hypothesis(path)


# ── filters ─────────────────────────────────────────────────────────────────

ROWS = pd.DataFrame({
    "close": [1.0, 2.0, 3.0, np.nan, 5.0],
    "w1_trend": ["UP", "DOWN", "NEUTRAL", "UP", None],
    "h4_index": [2, 3, 4, 5, 2],
    "in_window": [True, False, True, True, False],
})
COLUMNS = set(ROWS.columns)


@pytest.mark.parametrize("expression, expected, nulls", [
    ("", [True] * 5, 0),
    ("close > 1.5", [False, True, True, False, True], 1),
    ("close >= 2 and w1_trend == 'DOWN'", [False, True, False, False, False], 2),
    ("w1_trend == 'UP' or h4_index in [3, 4]", [True, True, True, True, False], 1),
    ("not in_window", [False, True, False, False, True], 0),
    ("h4_index not in (2, 5)", [False, True, True, False, False], 0),
    ("1 < close <= 3", [False, True, True, False, False], 1),
    ("close > -1", [True, True, True, False, True], 1),
    ("in_window and h4_index != 4", [True, False, False, True, False], 0),
])
def test_filters_accept_comparisons_in_and_or_not(expression, expected, nulls):
    f = compile_filter(expression, COLUMNS)
    mask, null = f.evaluate(ROWS)
    assert list(mask) == expected
    assert int(null.sum()) == nulls                           # rows with a null column read: skipped and counted
    assert not (mask & null).any()


@pytest.mark.parametrize("expression, offending", [
    ("abs(close) > 1", "Call"),
    ("close.real > 1", "Attribute"),
    ("close[0] > 1", "Subscript"),
    ("(lambda: 1)() == 1", "Call"),
    ("close + 1 > 2", "BinOp"),
    ("__import__('os')", "Call"),
    ("close > 1 if in_window else False", "IfExp"),
    ("unknown > 1", "unknown"),
    ("close >", "syntax"),
])
def test_filters_refuse_anything_else(expression, offending):
    with pytest.raises(FilterError, match=offending):
        compile_filter(expression, COLUMNS)


def test_filter_names_forbidden_label_columns():
    with pytest.raises(FilterError, match="rem_move.*label"):
        compile_filter("rem_move > 0", COLUMNS, forbidden={"rem_move": "a label column"})


def test_filter_reports_the_columns_it_reads():
    assert compile_filter("close > 1 and w1_trend == 'UP'", COLUMNS).columns == {"close", "w1_trend"}
