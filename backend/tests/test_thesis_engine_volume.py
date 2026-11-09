"""
Tests for Volume Profile on the Thesis Engine (Requirements 25-26; task 442): the profile's arithmetic, nothing later
read, each gate, the POC entry, V1 unchanged, the registered pick, and one window end to end. No market data is read.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from tests.thesis_engine_walks import walk_m1
from thesis_engine import hao
from thesis_engine.replay import prepare, run
from thesis_engine.settings import V1, V2
from thesis_engine.thesis import research_theses
from thesis_engine.volume import Profile, Profiles, build, passes

FIVE = 5 * 60 * 1_000_000_000


def _walk(weeks: int = 14, seed: int = 5, volume: bool = True) -> pd.DataFrame:
    m1 = walk_m1(weeks, seed=seed, step=0.0003, spread=0.00003)
    if volume:
        m1["tick_volume"] = np.random.default_rng(seed).integers(1, 100, len(m1))
    return m1


def _theses(mk, arm: str = "ORACLE"):
    theses, _ = research_theses("EURUSD", mk.book, arm, seed=1, s=V1, since_from=0)
    return theses


def test_a_bars_volume_is_spread_over_the_bins_it_traded():
    p = build(np.array([0.0, 2.0]), np.array([10.0, 2.5]), np.array([10.0, 5.0]), bins=10)
    assert np.allclose(p.volume, [1, 1, 6, 1, 1, 1, 1, 1, 1, 1])
    assert np.isclose(p.volume.sum(), 15.0)
    assert np.isclose(p.poc, 2.5)
    # 70% of 15 is 10.5: bin 2 (6), then both neighbours on the ties (8, 10), then the only one left above (11)
    assert np.isclose(p.val, 0.0) and np.isclose(p.vah, 6.0)


def test_the_value_area_takes_the_larger_neighbour_and_holds_its_share():
    p = build(np.array([0.0, 2.1, 3.1, 1.1]), np.array([10.0, 2.9, 3.9, 1.9]), np.array([10.0, 20.0, 4.0, 2.0]), bins=10)
    assert np.isclose(p.poc, 2.5)                      # bin 2 holds 21
    # 70% of 36 is 25.2: bin 2 (21), the larger neighbour bin 3 (5 -> 26)
    assert np.isclose(p.val, 2.0) and np.isclose(p.vah, 4.0)
    inside = p.volume[int(round((p.val - p.low) / p.width)):int(round((p.vah - p.low) / p.width))].sum()
    assert inside >= 0.7 * p.volume.sum()


def test_a_tied_poc_is_nearest_the_middle_then_the_lower():
    lows, highs, vols = np.array([0.0, 1.2, 5.2]), np.array([7.0, 1.4, 5.4]), np.array([7.0, 3.0, 3.0])
    assert np.isclose(build(lows, highs, vols, bins=7).poc, 1.5)        # bins 1 and 5, both two from the middle
    lows, highs, vols = np.array([0.0, 1.2, 5.2]), np.array([8.0, 1.4, 5.4]), np.array([8.0, 3.0, 3.0])
    assert np.isclose(build(lows, highs, vols, bins=8).poc, 5.5)        # 5 is nearer the middle, 3.5, than 1


def test_no_range_or_no_volume_is_no_profile():
    assert build(np.array([1.0]), np.array([1.0]), np.array([5.0]), bins=10) is None
    assert build(np.array([1.0]), np.array([2.0]), np.array([0.0]), bins=10) is None
    assert build(np.array([]), np.array([]), np.array([]), bins=10) is None


def test_only_the_last_closed_period_is_read():
    m1 = _walk(6)
    mk = prepare("EURUSD", m1, V1)
    w1 = mk.book.frames["W1"].c
    t = int(w1.end[2]) + 3 * 3600 * 1_000_000_000        # inside the fourth week
    before = mk.profiles.previous(w1, t, 100)
    later = m1["time"] >= pd.Timestamp(w1.end[2], tz="UTC")
    changed = m1.assign(tick_volume=np.where(later, 9999, m1["tick_volume"]),
                        high=np.where(later, m1["high"] + 1.0, m1["high"]))
    after = prepare("EURUSD", changed, V1).profiles.previous(w1, t, 100)
    assert np.array_equal(before.volume, after.volume) and before.poc == after.poc
    assert mk.profiles.previous(w1, int(w1.end[0]) - 1, 100) is None     # nothing has closed yet


def _profile() -> Profile:
    return Profile(low=0.0, width=1.0, volume=np.array([0, 1, 1, 8, 8, 8, 1, 1, 0, 0], dtype=float),
                   poc=4.5, vah=6.0, val=3.0)


@pytest.mark.parametrize("gate,bull,entry,extreme,expected", [
    ("POC", True, 4.5, 2.0, True), ("POC", True, 4.6, 2.0, False),
    ("POC", False, 4.5, 7.0, True), ("POC", False, 4.4, 7.0, False),
    ("VA", True, 3.0, 2.0, True), ("VA", True, 3.1, 2.0, False),
    ("VA", False, 6.0, 7.0, True), ("VA", False, 5.9, 7.0, False),
    ("NEAR", True, 9.0, 3.2, True), ("NEAR", True, 9.0, 1.5, False),
    ("NEAR", False, 0.0, 6.2, True), ("NEAR", False, 0.0, 8.0, False),
])
def test_each_gate_reads_its_side(gate, bull, entry, extreme, expected):
    assert passes(gate, _profile(), bull, entry, risk=1.0, extreme=extreme, adr=1.0, near_adr=0.25, rr=2.0) is expected


def test_the_path_gate_reads_what_lies_ahead_and_outside_is_empty():
    p = _profile()
    assert np.isclose(p.density(3.0, 5.0), 8.0 / p.volume.mean())
    assert passes("PATH", p, True, entry=6.0, risk=1.0, extreme=5.0, adr=1.0, near_adr=0.25, rr=2.0)      # 1 a bin
    assert not passes("PATH", p, True, entry=3.0, risk=1.0, extreme=2.0, adr=1.0, near_adr=0.25, rr=2.0)  # 8 a bin
    assert passes("PATH", p, True, entry=20.0, risk=1.0, extreme=19.0, adr=1.0, near_adr=0.25, rr=2.0)    # beyond it
    assert not passes("PATH", p, False, entry=6.0, risk=1.0, extreme=7.0, adr=1.0, near_adr=0.25, rr=2.0)  # 8 a bin
    assert not passes("POC", None, True, 1.0, 1.0, 0.5, 1.0, 0.25, 2.0)


@pytest.mark.parametrize("s", [V1, V2])
def test_the_older_settings_journal_the_same_with_volume_in_the_bars(s):
    with_v, without = prepare("EURUSD", _walk(10), V1), prepare("EURUSD", _walk(10, volume=False), V1)
    assert with_v.profiles is not None and without.profiles is None
    theses = _theses(without)
    assert theses
    assert run(with_v, theses, s, slippage=0.00001).lines() == run(without, theses, s, slippage=0.00001).lines()


def test_a_setting_that_needs_volume_refuses_bars_without_it():
    mk = prepare("EURUSD", _walk(4, volume=False), V1)
    with pytest.raises(ValueError, match="tick volume"):
        run(mk, [], replace(V1, version="x", volume_gate="POC"))
    with pytest.raises(ValueError, match="tick volume"):
        run(mk, [], replace(V1, version="x", entry="LIMIT_POC"))


def test_a_gate_skips_and_every_order_it_lets_through_clears_it():
    mk = prepare("EURUSD", _walk(), V1)
    theses = _theses(mk)
    base = run(mk, theses, V1, slippage=0.00001)
    j = run(mk, theses, replace(V1, version="poc", volume_gate="POC"), slippage=0.00001)
    assert any(r["reason"] == "VOLUME" for r in j.of("skip"))
    assert len(j.of("intent")) != len(base.of("intent")) or j.lines() != base.lines()
    w1 = mk.book.frames["W1"].c
    assert j.of("intent")
    for i in j.of("intent"):
        p = mk.profiles.previous(w1, i["at"], V1.profile_bins, V1.value_area)
        assert i["entry"] <= p.poc if i["side"] == "BULLISH" else i["entry"] >= p.poc
    assert not any(r["reason"] == "VOLUME" for r in base.of("skip"))


def test_the_poc_entry_is_a_limit_at_the_legs_poc_and_reads_nothing_later():
    mk = prepare("EURUSD", _walk(), V1)
    theses = _theses(mk)
    j = run(mk, theses, replace(V1, version="epoc", entry="LIMIT_POC"), slippage=0.00001)
    limits = [i for i in j.of("intent") if i["kind"] == "LIMIT"]
    assert limits
    sweeps = [n["t"] for n in j.of("note") if n["note"] == "sweep"]
    for i in limits:
        start = max(t for t in sweeps if t <= i["at"]) - FIVE
        assert np.isclose(i["entry"], mk.profiles.leg_poc(start, i["at"], V1.leg_bins))
        assert i["entry"] > i["stop"] if i["side"] == "BULLISH" else i["entry"] < i["stop"]
    assert {r["event"] for r in j.of("fill")} & {"FILLED", "EXPIRED"}


def _tab(rows):
    return pd.DataFrame([{"window": w, "variant": v, "p_week": p, "ORACLE_week": o, "ORACLE_trades": n}
                         for w, v, p, o, n in rows])


def test_the_pick_needs_trades_and_epoc_must_beat_the_plain_limit():
    rows = []
    for w, base in (("a", 0.58), ("b", 0.50), ("c", 0.59), ("pooled", 0.56)):
        rows += [(w, "V1", base, 0.7, 400), (w, "POC_W", base - 0.03, 0.6, 200),
                 (w, "VA_W", base - 0.09, 0.5, 50),            # the lowest, on an eighth of the trades
                 (w, "MT", base - 0.08, 0.5, 300),             # a control, whatever its numbers
                 (w, "EPOC", base - 0.05, 0.5, 300)]           # good, but no better than the plain limit
    chosen, why = hao.pick(_tab(rows))
    assert chosen == "POC_W"
    assert not why["VA_W"]["qualifies"] and not why["VA_W"][hao.KEPT]
    assert not why["MT"]["qualifies"] and not why["EPOC"]["qualifies"]
    assert not why["EPOC"]["below MT pooled (EPOC only)"]
    no_mt, _ = hao.pick(_tab([r for r in rows if r[1] in ("V1", "EPOC")]))
    assert no_mt == "EPOC"
    none, _ = hao.pick(_tab([r for r in rows if r[1] in ("V1", "VA_W", "MT")]))
    assert none is None


def test_the_registered_variants_are_v1_with_one_change():
    assert list(hao.VARIANTS)[0] == "V1" and len(hao.VARIANTS) == 10
    for name, s in hao.VARIANTS.items():
        changed = [f for f in s.__dataclass_fields__ if f != "version" and getattr(s, f) != getattr(V1, f)]
        if name == "V1":
            assert not changed
        elif name in ("EPOC", "MT"):
            assert changed == ["entry"]
        else:
            assert changed in (["volume_gate"], ["volume_gate", "volume_anchor"])
    assert hao.VARIANTS["POC_W"].volume_anchor == "W1" and hao.VARIANTS["POC_D"].volume_anchor == "D1"


def test_one_window_end_to_end(tmp_path, monkeypatch):
    _walk().to_parquet(tmp_path / "EURUSD_M1.parquet")
    monkeypatch.setattr(hao, "MARKETS", ("EURUSD",))
    trades, held, funnel = hao.windows({"walk": (tmp_path, None, 0, None)}, ("V1", "POC_W", "EPOC", "MT"))
    assert set(trades["variant"]) == {"V1", "POC_W", "EPOC", "MT"} and set(held["arm"]) == set(hao.ARMS)
    tab = hao.table(trades, held)
    assert set(tab["window"]) == {"walk"} and (tab["p_week"] <= 1).all()
    f = funnel.groupby("variant")[["orders", "limits", "volume_skips"]].sum()
    assert f.loc["POC_W", "volume_skips"] > 0 and f.loc["V1", "volume_skips"] == 0
    assert f.loc["V1", "limits"] == 0 and f.loc["MT", "limits"] > 0 and f.loc["EPOC", "limits"] > 0
