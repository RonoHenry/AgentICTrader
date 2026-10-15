"""
Tests for liquidity_engine/context/ — the Model A reader (context-engine Requirement 13, update 2026-10-15).

Task 310 (.kiro/specs/context-engine/tasks.md). A hand-built day on a small frame set (F = H1, C = M5, E = M1),
drawn as straight M1 legs between waypoints, puts each step of a short where it should be:
- an H1 range 100-110 with an untaken swing high at 110 (the POI);
- price back in premium; C1 at 12:00; C2 runs C1's high into the POI at 12:07;
- a displacement and C2's close back under C1's high; C3 retraces into the OTE and fills;
- then TP1 (C1's low) and -1 SD, until the H1 candle closes.
Each invalidation changes one leg of it. The measures are held to the engine's own CISD and order blocks, and
three properties run on random walks.
Validates: Requirements 13.1-13.6 (.kiro/specs/context-engine/requirements.md); Properties 1, 2, 10
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from liquidity_engine.context.frame_state import DealingRange, bearish_pois, dealing_range
from liquidity_engine.context.measures import bearish_cisd, bearish_fvgs, bearish_order_blocks, mirror
from liquidity_engine.context.model_a import FrameSet, ModelAReader, Variant, in_time_window
from liquidity_engine.detectors.internal import PDArrayDetector
from liquidity_engine.ipda.cisd import CISDDetector
from liquidity_engine.models import BiasDirection, Candle, Timeframe

SMALL = FrameSet("small", "H1", "M5", "M1")
DAY = int(datetime(2025, 1, 7, tzinfo=timezone.utc).timestamp())         # a Tuesday, as New York wall seconds
WICK = 0.02

# the hand-built day: (minute after 00:00 New York, price)
HISTORY = [(0, 100), (180, 105), (210, 110), (240, 108.5), (450, 100), (480, 100.5), (600, 104), (715, 108.4),
           (720, 108.4)]
C1 = [(725, 108.6)]                                    # 12:00-12:04, rising: its low 108.38 is TP1
C2 = [(728, 110.2), (729, 108.9), (730, 107.6)]        # 12:05-12:09: into the POI, then the displacement
C3 = [(734, 109.6), (735, 109.0)]                      # 12:10-12:14: back into the OTE, filled
AFTER = [(775, 104.0), (790, 104.2)]                   # down through TP1 and -1 SD; the H1 candle closes at 13:00


def wall(minute: int) -> int:
    return DAY + 60 * minute


def m1(points, wick=WICK):
    """M1 bars along straight lines between (minute, price) waypoints."""
    t, o, h, l, c = [], [], [], [], []
    for (m0, p0), (m_1, p1) in zip(points, points[1:]):
        for k in range(m0, m_1):
            a = p0 + (p1 - p0) * (k - m0) / (m_1 - m0)
            b = p0 + (p1 - p0) * (k + 1 - m0) / (m_1 - m0)
            t.append(wall(k)); o.append(a); h.append(max(a, b) + wick); l.append(min(a, b) - wick); c.append(b)
    return np.array(t, dtype=np.int64), np.array(o), np.array(h), np.array(l), np.array(c)


def read(points, side="SHORT", variant=Variant(), frames=SMALL):
    t, o, h, l, c = m1(points)
    return ModelAReader(frames, t, o, h, l, c, side=side, variant=variant).run(int(t[0]), int(t[-1]) + 60)


def the_one(instances, c1_minute=720):
    """The instance whose C1 is the 12:00 candle."""
    found = [x for x in instances if x["c1_open"] == wall(c1_minute)]
    assert found, [(x["c1_open"], x["end"]) for x in instances][-5:]
    return found[0]


def day(c2=C2, c3=C3, after=AFTER, c1=C1):
    return HISTORY + c1 + c2 + c3 + after


# ── the sequence ───────────────────────────────────────────────────────────

def test_short_runs_framed_to_tp1():
    x = the_one(read(day()))
    s = x["states"]
    assert list(s)[:7] == ["FRAMED", "ARMED", "MANIPULATED", "DISPLACED", "REJECTED", "IN_OTE", "ENTERED"]
    assert s["FRAMED"] == wall(725) and s["MANIPULATED"] == wall(728) and s["DISPLACED"] == wall(730)
    assert s["REJECTED"] == wall(730) and s["ENTERED"] == wall(734)
    assert x["poi_kind"] == "SWING_HIGH" and x["poi_near"] < 110.02 < x["poi_far"]
    assert x["c2_extreme"] == pytest.approx(110.22) and x["range_end"] == pytest.approx(107.58)
    size = 110.22 - 107.58
    assert x["entry"] == pytest.approx(107.58 + 0.705 * size)
    assert x["ote_near"] == pytest.approx(107.58 + 0.62 * size) and x["ote_far"] == pytest.approx(107.58 + 0.79 * size)
    assert x["tp1"] == pytest.approx(108.38) and x["sd1"] == pytest.approx(107.58 - size)
    assert x["stop"] > 110.22 and x["fill"] == pytest.approx(x["entry"])
    assert "TP1" in s and "SD_1" in s and "SD_2" not in s
    assert x["end"] == "HORIZON" and x["end_at"] == wall(780)
    risk = x["stop"] - x["fill"]
    assert x["r_tp1"] == pytest.approx((x["fill"] - 108.38) / risk)
    assert x["mfe_r"] >= (x["fill"] - x["sd1"]) / risk


def test_long_mirrors_it():
    mirrored = [(m, 220 - p) for m, p in day()]
    short, long = the_one(read(day())), the_one(read(mirrored, side="LONG"))
    assert long["side"] == "LONG" and long["states"] == short["states"] and long["end"] == short["end"]
    for key in ("entry", "stop", "tp1", "sd1", "c2_extreme", "range_end", "poi_near", "poi_far"):
        assert long[key] == pytest.approx(220 - short[key]), key
    assert long["r_tp1"] == pytest.approx(short["r_tp1"])


def test_no_manipulation_without_c1_high_into_poi():
    x = the_one(read(day(c2=[(728, 109.5), (729, 108.9), (730, 107.6)])))
    assert x["end"] == "NO_MANIPULATION" and x["end_at"] == wall(730) and "MANIPULATED" not in x["states"]


def test_no_rejection():
    x = the_one(read(day(c2=[(728, 110.2), (729, 109.5), (730, 108.8)])))
    assert x["end"] == "NO_REJECTION" and "REJECTED" not in x["states"]


def test_poi_failed():
    x = the_one(read(day(c2=[(728, 110.6), (730, 110.5)])))
    assert x["end"] == "POI_FAILED"


def test_missed_when_the_low_breaks_before_the_ote():
    x = the_one(read(day(c3=[(732, 107.0), (733, 108.3), (735, 109.6)])))
    assert x["end"] == "MISSED" and x["end_at"] == wall(731)


def test_retrace_invalid_without_displacement():
    x = the_one(read(day(c2=[(728, 110.2), (730, 108.5)], c3=[(735, 110.5)])))
    assert "DISPLACED" not in x["states"] and x["end"] == "RETRACE_INVALID"


def test_expired_without_a_fill():
    x = the_one(read(day(c3=[(734, 108.9), (735, 108.5)])))
    assert x["end"] == "EXPIRED" and x["end_at"] == wall(735) and "ENTERED" not in x["states"]
    assert x["end_reason"] == "C3 closed without a fill"


def test_new_range_end_cisd_and_swing():
    c3 = [(732, 107.0), (733, 108.3), (735, 109.6)]
    cisd = the_one(read(day(c3=c3), variant=Variant(leg_end="CISD")))
    swing = the_one(read(day(c3=c3), variant=Variant(leg_end="SWING")))
    assert cisd["end"] == "MISSED"
    assert swing["range_end"] == pytest.approx(106.98) and "ENTERED" in swing["states"]
    assert swing["entry"] == pytest.approx(106.98 + 0.705 * (110.22 - 106.98))


def test_displacement_needs_body_and_fvg():
    t, o, h, l, c = m1(day())
    first = int(np.searchsorted(t, wall(728)))
    for k in range(first, first + 10):                     # wicks back up into every gap: no FVG anywhere in the leg
        h[k] = max(h[k], l[k - 2])
    no_fvg = the_one(ModelAReader(SMALL, t, o, h, l, c).run(int(t[0]), int(t[-1]) + 60))
    assert "DISPLACED" not in no_fvg["states"] and no_fvg["end"] == "EXPIRED"
    assert no_fvg["end_reason"] == "C3 closed without displacement"
    big_body = the_one(read(day(), variant=Variant(displacement_body=10)))
    assert "DISPLACED" not in big_body["states"]


def test_the_engines_cisd_is_a_variant():
    x = the_one(read(day(), variant=Variant(cisd="NEXT")))
    assert "ENTERED" in x["states"] or "DISPLACED" not in x["states"]       # recorded either way; the reading differs


def test_inducement_recorded_not_gating():
    plain = the_one(read(day()))
    equal = the_one(read(day(c1=[(721, 108.6), (723, 108.3), (724, 108.6), (725, 108.5)])))
    assert plain["inducement"] is None and equal["inducement"] == "EQUAL_HIGHS"
    assert "MANIPULATED" in equal["states"] and "ENTERED" in equal["states"]


def test_time_sync_recorded():
    at = lambda h, m=0: int(datetime(2025, 1, 7, h, m, tzinfo=timezone.utc).timestamp())  # noqa: E731
    assert in_time_window("H1", at(2)) and in_time_window("H1", at(8)) and not in_time_window("H1", at(10))
    assert in_time_window("M15", at(9, 45)) and in_time_window("M15", at(10)) and not in_time_window("M15", at(10, 15))
    assert in_time_window("H4", at(5)) and not in_time_window("H4", at(13))
    assert in_time_window("D1", at(17) - 86400) and not in_time_window("D1", at(17) + 86400)   # Tue's, not Thu's
    x = the_one(read(day()))
    assert x["time_sync"] is False                           # an M5 C2: no window of the trader's covers it


def test_one_instance_per_direction():
    out = read(day())
    x = the_one(out)
    framed = [y["states"]["FRAMED"] for y in out]
    assert not [t for t in framed if x["states"]["FRAMED"] < t < x["end_at"]]


# ── the measures, held to the engine ───────────────────────────────────────

def random_bars(seed, n=300):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 0.05, n)
    h = np.maximum(o, c) + rng.random(n) * 0.4
    l = np.minimum(o, c) - rng.random(n) * 0.4
    return o, h, l, c


def candles(o, h, l, c):
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [Candle(timestamp=t0 + timedelta(hours=i), open=o[i], high=h[i], low=l[i], close=c[i], timeframe=Timeframe.H1,
                   instrument="XAUUSD") for i in range(len(o))]


@settings(max_examples=25, deadline=None)
@given(st.integers(0, 10_000))
def test_cisd_equals_the_engines(seed):
    o, h, l, c = random_bars(seed, 120)
    cs = candles(o, h, l, c)
    det = CISDDetector()
    for j in range(1, len(cs)):
        res = det.detect(cs[:j + 1])
        engine = res is not None and res.confirmed and res.direction == BiasDirection.BEARISH
        assert bearish_cisd(o, h, l, c, j) == engine, j


@settings(max_examples=25, deadline=None)
@given(st.integers(0, 10_000))
def test_order_blocks_equal_the_engines(seed):
    o, h, l, c = random_bars(seed)
    engine = [(round(a.low, 9), round(a.high, 9)) for a in PDArrayDetector()._detect_order_blocks(candles(o, h, l, c), Timeframe.H1)
              if a.direction == BiasDirection.BEARISH]
    mine = [(round(lo, 9), round(hi, 9)) for _j, _i, lo, hi in bearish_order_blocks(o, h, l, c)]
    assert mine == engine


def test_fvg_is_the_gap_only():
    o = np.array([10.0, 9.5, 8.0]); h = np.array([10.2, 9.6, 8.2]); l = np.array([9.8, 8.1, 7.9]); c = np.array([9.9, 8.2, 8.0])
    assert bearish_fvgs(h, l, 0, 3) == [(2, 8.2, 9.8)]                     # from candle 3's high to candle 1's low


def test_dealing_range_and_premium_pois():
    t, o, h, l, c = m1(HISTORY)
    from algo_research.replay.timeframes import aggregate
    f = aggregate(t, o, h, l, c, "H1")
    rng = dealing_range(f["high"].to_numpy(), f["low"].to_numpy(), len(f))
    assert rng.high == pytest.approx(110.02) and rng.low == pytest.approx(99.98) and rng.zone(108.6) == "PREMIUM"
    pois = bearish_pois(f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(), len(f),
                        108.6, rng, 2.0, tf="H1")
    assert pois and pois[0].kind == "SWING_HIGH" and pois[0].low < 110.02 < pois[0].high
    assert DealingRange(100, 110, 0, 1).zone(104) == "DISCOUNT" and DealingRange(100, 110, 0, 1).zone(105) == "EQUILIBRIUM"


# ── properties on random walks ─────────────────────────────────────────────

def walk(seed, minutes=3 * 1440):
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 0.08, minutes) + 0.25 * np.sin(np.arange(minutes) / 180.0) * rng.normal(1, 0.3)
    c = 100 + np.cumsum(steps)
    o = np.r_[100.0, c[:-1]]
    h = np.maximum(o, c) + rng.random(minutes) * 0.06
    l = np.minimum(o, c) - rng.random(minutes) * 0.06
    t = DAY + 60 * np.arange(minutes, dtype=np.int64)
    return t, o, h, l, c


ORDER = ["FRAMED", "ARMED", "MANIPULATED", "REJECTED", "DISPLACED", "IN_OTE", "ENTERED"]


@settings(max_examples=12, deadline=None)
@given(st.integers(0, 10_000), st.sampled_from(["SHORT", "LONG"]))
def test_property_10_the_sequence_holds(seed, side):
    t, o, h, l, c = walk(seed)
    for x in ModelAReader(SMALL, t, o, h, l, c, side=side).run(int(t[0]), int(t[-1])):
        s = x["states"]
        assert next(iter(s)) == "FRAMED"
        if "REJECTED" in s or "DISPLACED" in s:
            assert "MANIPULATED" in s and s["MANIPULATED"] <= min(s.get("REJECTED", 1e18), s.get("DISPLACED", 1e18))
        if "ENTERED" in s:
            assert s["REJECTED"] <= s["ENTERED"] and s["DISPLACED"] <= s["ENTERED"]
        assert all(when <= x["end_at"] for when in s.values())


@settings(max_examples=10, deadline=None)
@given(st.integers(0, 10_000), st.integers(600, 3 * 1440 - 60))
def test_property_2_only_the_past(seed, cut):
    t, o, h, l, c = walk(seed)
    full = ModelAReader(SMALL, t, o, h, l, c).run(int(t[0]), int(t[-1]))
    part = ModelAReader(SMALL, t[:cut], o[:cut], h[:cut], l[:cut], c[:cut]).run(int(t[0]), int(t[-1]))
    end = int(t[cut - 1])
    done = [x for x in full if x["end_at"] < end - 3600]                        # ended well before the cut
    assert [x["events"] for x in done] == [x["events"] for x in part[:len(done)]]


@settings(max_examples=8, deadline=None)
@given(st.integers(0, 10_000), st.floats(0.5, 20.0), st.floats(-50.0, 500.0))
def test_property_1_sizes_are_the_frames_own(seed, scale, shift):
    """Prices in any unit and at any level, and the same week a week later, read the same states."""
    t, o, h, l, c = walk(seed)
    base = ModelAReader(SMALL, t, o, h, l, c).run(int(t[0]), int(t[-1]))
    moved = ModelAReader(SMALL, t + 7 * 86400, *(x * scale + shift for x in (o, h, l, c))).run(int(t[0]) + 7 * 86400,
                                                                                              int(t[-1]) + 7 * 86400)
    strip = lambda xs, dt: [(x["end"], {k: v - dt for k, v in x["states"].items()}) for x in xs]  # noqa: E731
    assert strip(base, 0) == strip(moved, 7 * 86400)


def test_legacy_fingerprint_leaves_the_context_package_out(tmp_path):
    """MA-D12: Model A's code doesn't touch the cached legacy runs' key."""
    from algo_backtester.cache import ENGINE_SOURCES, engine_code_fingerprint
    for pattern in ENGINE_SOURCES:
        if "*" not in pattern:
            (tmp_path / pattern).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / pattern).write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "liquidity_engine" / "context").mkdir(parents=True)
    (tmp_path / "liquidity_engine" / "engine.py").write_text("legacy = 1\n", encoding="utf-8")
    (tmp_path / "liquidity_engine" / "context" / "model_a.py").write_text("a = 1\n", encoding="utf-8")
    before = engine_code_fingerprint(tmp_path)
    (tmp_path / "liquidity_engine" / "context" / "model_a.py").write_text("a = 2\n", encoding="utf-8")
    assert engine_code_fingerprint(tmp_path) == before
    (tmp_path / "liquidity_engine" / "engine.py").write_text("legacy = 2\n", encoding="utf-8")
    assert engine_code_fingerprint(tmp_path) != before


# ── volatility and time (Requirement 18, update 2026-10-15b) ───────────────

def with_history(points, daily_range, days=15):
    """``points`` after ``days`` of a plain daily swing of ``daily_range``, ending at 100 at 00:00 on the day."""
    import math
    hist = [(-days * 1440 + k, 100 + daily_range / 2 * math.sin(2 * math.pi * k / 1440)) for k in range(0, days * 1440, 10)]
    return hist + points


def test_day_phase_labels():
    from liquidity_engine.context.model_a import day_phase
    at = lambda h, m=0: int(datetime(2025, 1, 7, h, m, tzinfo=timezone.utc).timestamp())  # noqa: E731
    assert [day_phase("M15", at(h, m)) for h, m in ((21, 0), (1, 0), (3, 0), (6, 0), (8, 0), (12, 5), (14, 0), (17, 30))] == \
           ["ASIA", "MIDNIGHT", "LONDON", "PRE_NY", "NY_AM", "NY_MID", "NY_PM", "CLOSE"]
    assert day_phase("H1", at(13, 30)) == "NY_PM" and day_phase("D1", at(17) - 86400) == "TUE"
    assert day_phase("W1", int(datetime(2025, 1, 19, 17, tzinfo=timezone.utc).timestamp())) == "WEEK3"


def test_phase_gate_frames_only_in_its_phases():
    from liquidity_engine.context.model_a import EARLY
    early = [x for x in read(day(), variant=Variant(phases=EARLY)) if x["c1_open"] == wall(720)]
    noon = the_one(read(day(), variant=Variant(phases=("NY_MID",))))
    assert not early and noon["phase"] == "NY_MID" and "ENTERED" in noon["states"]
    assert the_one(read(day()))["phase"] == "NY_MID"                      # recorded without a gate too


def test_adr_and_its_gates():
    pts = with_history(day(), 60)
    x = the_one(read(pts, variant=Variant(size_basis="SEASONAL")))
    assert x["adr"] == pytest.approx(60, rel=0.05) and "ENTERED" in x["states"]
    day_low = 100 + 30 * np.sin(2 * np.pi * np.arange(-420, 0, 10) / 1440).min() - WICK      # since 17:00
    assert x["adr_used"] == pytest.approx((110.22 - day_low) / x["adr"], rel=0.02)
    assert x["size_adr"] == pytest.approx((110.22 - 108.38) / x["adr"], rel=0.01)
    assert the_one(read(pts, variant=Variant(max_adr_used=0.5)))["end"] == "RANGE_SPENT"
    assert the_one(read(pts, variant=Variant(max_size_adr=0.01)))["end"] == "TOO_LARGE"
    small = the_one(read(with_history(day(), 1.5), variant=Variant(room=True)))
    assert small["end"] == "NO_ROOM" and small["target_reach"] > 1
    assert "REJECTED" not in small["states"]                               # gated before REJECTED: no premise counted


def test_no_gate_without_enough_history():
    x = the_one(read(day(), variant=Variant(max_adr_used=0.1, max_size_adr=0.01, room=True)))
    assert x["adr"] is None and "ENTERED" in x["states"]                    # one day of data: no ADR, never gated


def test_seasonal_sizes_read_the_same_hour_on_earlier_days():
    t, o, h, l, c = m1(day())
    r = ModelAReader(SMALL, t, o, h, l, c, variant=Variant(size_basis="SEASONAL"))
    days, per = 8, 1440
    et = np.array([DAY - (days - d) * 86400 + 60 * k for d in range(days) for k in range(per)], dtype=np.int64)
    width = np.array([(1.0 + d) * (2.0 if 600 <= k < 615 else 1.0) for d in range(days) for k in range(per)])
    sizes = r._sizes(et, 100 + width / 2, 100 - width / 2, 60)
    last = (days - 1) * per
    slot = ((et - 61200) % 86400) // 900
    k = last + 605                                                           # 10:05 on the last day: slot 10:00-10:15
    same_slot_before = [width[i] for i in range(last) if slot[i] == slot[k] and (et[i] - 61200) // 86400 < (et[k] - 61200) // 86400]
    days_before = sorted({(et[i] - 61200) // 86400 for i in range(last) if slot[i] == slot[k]})[-20:]
    expect = np.mean([np.mean([width[i] for i in range(last) if slot[i] == slot[k] and (et[i] - 61200) // 86400 == dd])
                      for dd in days_before])
    assert sizes[k] == pytest.approx(expect) and same_slot_before


@settings(max_examples=5, deadline=None)
@given(st.integers(0, 10_000), st.integers(9 * 1440, 12 * 1440 - 60))
def test_property_2_holds_with_volatility_and_time(seed, cut):
    from liquidity_engine.context.model_a import MODEL_A_VT
    t, o, h, l, c = walk(seed, minutes=12 * 1440)
    full = ModelAReader(SMALL, t, o, h, l, c, variant=MODEL_A_VT).run(int(t[0]), int(t[-1]))
    part = ModelAReader(SMALL, t[:cut], o[:cut], h[:cut], l[:cut], c[:cut], variant=MODEL_A_VT).run(int(t[0]), int(t[-1]))
    end = int(t[cut - 1])
    done = [x for x in full if x["end_at"] < end - 3600]
    assert [x["events"] for x in done] == [x["events"] for x in part[:len(done)]]
    assert all(x["phase"] in ("ASIA", "MIDNIGHT", "LONDON", "PRE_NY") for x in full)
