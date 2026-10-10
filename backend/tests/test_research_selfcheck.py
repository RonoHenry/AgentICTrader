"""
Self-validation of AlgoResearch: it finds nothing where there is nothing, finds
an edge where one is planted, and reproduces itself byte for byte.

Task 255 (.kiro/specs/algo-research/tasks.md).

- Simulated markets: driftless random walks of M1 over the FX week (Sunday
  17:00 to Friday 17:00 New York), with session-shaped volatility and a
  constant spread (tests/research_fixtures.py).
- Property 8 (marked ``slow``; it runs at checkpoints with ``-m slow``): on 200
  null worlds, a race hypothesis (asia_raid_reclaim, win rate against the coin
  flip) and a direction hypothesis (the last H4 candle's direction, accuracy
  against the best naive rule) pass in at most 5%. With a planted edge after
  the event, they pass in at least 90%, and the statistic's interval covers the
  planted expectation in at least 90%.
  - Planting: for the first event of a day, with probability q, the rest of the
    candle is replaced by a straight path in the event's direction (to beyond
    the race's target). The event itself is unchanged (it reads nothing after
    t). The planted expectation is then known: each planted event scores what
    its path gives, every other one its driftless expectation (p_coin for a
    race, 0.5 for a direction).
- The golden research run: a fixed synthetic data set and hypothesis give a
  byte-identical report and ledger row. Regenerate on purpose with
  ``UPDATE_GOLDEN=1 pytest tests/test_research_selfcheck.py`` (from backend/).

Validates: Requirements 14.1-14.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import csv
import io
import os
import random
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algo_research.frame import frame_from_arrays, ny_instant
from algo_research.hypothesis import parse_hypothesis
from algo_research.ledger import LEDGER_COLUMNS, ledger_row
from algo_research.report import ReportInputs, render_report
from algo_research.runner import RunSettings, run_test
from algo_research.stats import seed_from
from tests.research_fixtures import fx_minutes, research_data, simulated_frame

GOLDEN = Path(__file__).parent / "fixtures" / "research" / "golden"
FIRST_SUNDAY = date(2025, 1, 5)
WORLD_DAYS = 120
WORLDS = 200
SETTINGS = RunSettings(resamples=10_000, random_time_draws=0, shuffles=0)
PLANT = {"race": 0.50, "direction": 0.80}            # the share of first events a world plants (see design.md)

RACE = parse_hypothesis('''
id = "H991"
title = "Self-check: an Asian range raid, reclaimed, runs to the other side"
statement = "After a raid of one side of the Asian range and a close back inside, the other side trades first."
family = "selfcheck"
created = 2026-10-10

[event]
name = "asia_raid_reclaim"
params = { window = ["01:00", "09:00"], reclaim_within = 4 }

[measure]
kind = "race"

[trade]
stop = { kind = "level", name = "raid_extreme" }
target = { kind = "level", name = "asia_opposite" }
time_limit = "day_close"

[baselines]
use = ["coin_flip"]

[pass]
min_events = 20
min_days = 20
require = [{ stat = "win_rate", versus = "coin_flip" }]
''')

DIRECTION = parse_hypothesis('''
id = "H992"
title = "Self-check: the last H4 candle's direction calls the rest of the day"
statement = "At 09:00 New York, the rest of the day moves the way the 05:00 H4 candle closed."
family = "selfcheck"
created = 2026-10-10

[event]
name = "anchor"
params = { at = "09:00", direction_from = "prev_h4_dir" }

[measure]
kind = "direction"

[baselines]
use = ["naive:always_long", "naive:prev_day_dir", "naive:w1_trend", "naive:side_d1_open", "naive:side_midnight_open"]

[pass]
min_events = 20
min_days = 20
require = [{ stat = "accuracy", versus = "best_naive" }]
''')

TESTS = {"race": RACE.tests()[0], "direction": DIRECTION.tests()[0]}


@lru_cache(maxsize=None)
def world_times() -> pd.DatetimeIndex:
    return fx_minutes(FIRST_SUNDAY, WORLD_DAYS)


def slices() -> dict:
    return {"confirm": (date(2025, 1, 6), date(2026, 1, 1))}


# ── the simulated market ────────────────────────────────────────────────────

def test_simulated_market_follows_the_fx_week_with_session_volatility():
    times = world_times()
    frame = simulated_frame("EURUSD", times, np.random.default_rng(0).standard_normal(3 * len(times)))
    local = times.tz_convert("America/New_York")
    assert local[0].strftime("%a %H:%M") == "Sun 17:00" and not (local.weekday == 5).any()
    assert not ((local.weekday == 4) & (local.hour >= 17)).any() and not ((local.weekday == 6) & (local.hour < 17)).any()
    assert pd.Series((local.tz_localize(None) + pd.Timedelta(hours=7)).normalize()).nunique() == WORLD_DAYS
    moves = np.abs(np.diff(frame.m1["close"].to_numpy()))
    hour = local.hour[1:]
    assert moves[hour == 8].mean() > 2.5 * moves[hour == 21].mean()       # New York open vs Asia
    assert (frame.m1["spread"] == 0.0001).all()
    assert (frame.m1["high"] >= frame.m1[["open", "close"]].max(axis=1)).all()


# ── planting an edge ────────────────────────────────────────────────────────

def plant(frame, result, kind: str, q: float, rng: np.random.Generator):
    """A copy of ``frame`` where, for the first event of each day and with probability
    q, the rest of the candle runs straight in the event's direction."""
    a = {k: frame.arrays[k].copy() for k in ("time", "open", "high", "low", "close", "spread")}
    events = result.events
    if kind == "race":
        events = events.join(result.races[["target", "outcome"]])
        events = events[events["outcome"].isin(["TARGET", "STOP", "TIMEOUT"])]
    first = events.sort_values("t").groupby("trading_date", sort=True).head(1)
    planted = set()
    for e in first.itertuples():
        if rng.random() >= q:
            continue
        j0 = int(np.searchsorted(a["time"], pd.Timestamp(e.t).value, "left"))
        close = ny_instant(pd.DatetimeIndex([e.trading_date + pd.Timedelta(days=1)]), 17 * 60)[0].value
        end = int(np.searchsorted(a["time"], close, "left"))
        if end <= j0:
            continue
        sign = 1.0 if e.direction == "LONG" else -1.0
        entry = a["open"][j0]
        goal = entry + 1.5 * (e.target - entry) if kind == "race" else entry + sign * 0.004
        steps = np.arange(end - j0)
        level = entry + (goal - entry) * np.minimum(1.0, (steps + 1) / min(10, end - j0))
        opens = np.concatenate([[entry], level[:-1]])
        a["open"][j0:end], a["close"][j0:end] = opens, level
        a["high"][j0:end], a["low"][j0:end] = np.maximum(opens, level), np.minimum(opens, level)
        planted.add(pd.Timestamp(e.t))
    times = pd.DatetimeIndex(a["time"].astype("datetime64[ns]")).tz_localize("UTC")
    new = frame_from_arrays(frame.instrument, times, a["open"], a["high"], a["low"], a["close"], spread=a["spread"],
                            typical_spread=frame.typical_spread, stop_slippage=frame.stop_slippage)
    return new, planted


def planted_expectation(result, planted: set, kind: str) -> float:
    """The statistic's expectation given the planted paths: planted events score what
    their path gives; the others their driftless expectation."""
    keys = result.events["t"].map(pd.Timestamp).isin(planted).to_numpy()
    if kind == "race":
        races = result.races
        ok = races["outcome"].isin(["TARGET", "STOP", "TIMEOUT"]).to_numpy()
        values = np.where(keys, races["score"].to_numpy(dtype=float), races["p_coin"].to_numpy(dtype=float))
        return float(values[ok].mean())
    table = result.table
    ok = (table["n:accuracy"] > 0).to_numpy()
    values = np.where(keys, table["sum:accuracy"].to_numpy(), 0.5)
    return float(values[ok].mean())


def one_world(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    times = world_times()
    frame = simulated_frame("EURUSD", times, rng.standard_normal(3 * len(times)))
    data = research_data({"EURUSD": frame}, slices())
    out = {}
    for kind, test in TESTS.items():
        null = run_test(test, data, "confirm", {}, seed=seed, settings=SETTINGS)
        planted_frame, planted = plant(frame, null, kind, PLANT[kind], rng)
        result = run_test(test, research_data({"EURUSD": planted_frame}, slices()), "confirm", {}, seed=seed,
                          settings=SETTINGS)
        main = result.stats[result.main_stat]
        expected = planted_expectation(result, planted, kind)
        out[kind] = {"null": null.verdict, "null_events": null.n_events, "planted": result.verdict,
                     "covered": bool(main.lo <= expected <= main.hi), "planted_events": len(planted)}
    return out


def test_one_world_smoke():
    world = one_world(1)
    for kind in ("race", "direction"):
        assert world[kind]["null_events"] >= 20, (kind, world)
        assert world[kind]["planted_events"] > 0
        assert world[kind]["planted"] in ("PASS", "FAIL")


@pytest.mark.slow
def test_property_8_null_calibration_and_power(request):
    if "slow" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("Property 8 runs at checkpoints: pytest -m slow tests/test_research_selfcheck.py")
    with ProcessPoolExecutor(max_workers=min(12, os.cpu_count() or 1)) as pool:
        worlds = list(pool.map(one_world, range(WORLDS)))
    for kind in ("race", "direction"):
        null_passes = sum(w[kind]["null"] == "PASS" for w in worlds)
        planted_passes = sum(w[kind]["planted"] == "PASS" for w in worlds)
        covered = sum(w[kind]["covered"] for w in worlds)
        print(f"{kind}: null passes {null_passes}/{WORLDS}, planted passes {planted_passes}/{WORLDS}, "
              f"interval covers the planted expectation {covered}/{WORLDS}")
        assert null_passes <= 0.05 * WORLDS, kind
        assert planted_passes >= 0.90 * WORLDS, kind
        assert covered >= 0.90 * WORLDS, kind


# ── the golden research run ─────────────────────────────────────────────────

def golden_frames() -> dict:
    """Two instruments, six weeks, from Python's own seeded generator (stable across platforms)."""
    times = fx_minutes(FIRST_SUNDAY, 30)
    frames = {}
    for seed, (instrument, base, sigma, spread) in enumerate((("EURUSD", 1.1, 0.00006, 0.0001),
                                                               ("XAUUSD", 2650.0, 0.15, 0.2))):
        rng = random.Random(20261010 + seed)
        normals = np.array([rng.gauss(0.0, 1.0) for _ in range(3 * len(times))])
        frames[instrument] = simulated_frame(instrument, times, normals, base=base, sigma=sigma, spread=spread)
    return frames


def golden_outputs() -> tuple[str, str]:
    path = GOLDEN / "H990-golden.toml"
    from algo_research.hypothesis import load_hypothesis

    h = load_hypothesis(path)
    data = research_data(golden_frames(), {"explore": (date(2025, 1, 6), date(2025, 1, 20)),
                                           "confirm": (date(2025, 1, 20), date(2025, 2, 15))})
    results = [run_test(test, data, "confirm", {}, seed_from(h.sha256, test.index),
                        RunSettings(resamples=2000, random_time_draws=5, shuffles=20)) for test in h.tests()]
    inputs = ReportInputs(snapshot="golden", fingerprints={"EURUSD": "simulated", "XAUUSD": "simulated"},
                          code_commit="0" * 40, specs={"EURUSD": {"typical spread": 0.0001},
                                                       "XAUUSD": {"typical spread": 0.2}},
                          hypothesis_text=path.read_text(encoding="utf-8"),
                          ledger_rows={r.label: str(i + 1) for i, r in enumerate(results)})
    report = render_report(results, inputs)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=LEDGER_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for i, r in enumerate(results):
        writer.writerow(ledger_row(r, seq=i + 1, run_at="2026-10-10T00:00:00+00:00", snapshot="golden",
                                   code_commit="0" * 40, report="docs/research/reports/H990.md"))
    return report, buffer.getvalue()


def test_golden_research_run_is_byte_identical():
    report, ledger = golden_outputs()
    expected_report, expected_ledger = GOLDEN / "expected_report.md", GOLDEN / "expected_ledger.csv"
    if os.environ.get("UPDATE_GOLDEN"):
        expected_report.write_bytes(report.encode())
        expected_ledger.write_bytes(ledger.encode())
    assert report.encode() == expected_report.read_bytes().replace(b"\r\n", b"\n"), (
        "the golden research report changed: if intended, rerun with UPDATE_GOLDEN=1 and commit it")
    assert ledger.encode() == expected_ledger.read_bytes().replace(b"\r\n", b"\n")
    again = golden_outputs()
    assert again == (report, ledger)                                   # and the same on a second run
    assert "**EURUSD**" in report and "Races" in report and ",H990," in ledger
