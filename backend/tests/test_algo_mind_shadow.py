"""
Tests for algo_mind/shadow.py and the live parts of algo_mind/dis.py — the directional state in shadow on the
context page (context-engine Requirement 35.3-35.4, task 395).

On the Exness GBPUSD fixture (H1 for 2026, M1 for 26-30 Oct): the terminal's frames leave out a forming day and
week; the week checks say "turn" exactly where reader v0 finds one; and the week of 26 Oct opens BULLISH on the
trader's narrative, with Thursday's read ending in the trader's order.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from algo_mind.dis import reader_turns, terminal_market, week_checks
from algo_mind.shadow import last_close, read_market, thesis_table, write_shadow
from algo_research.sequence import NY

FIXTURES = Path(__file__).parent / "fixtures" / "research" / "sequence"
UTC = timezone.utc


def _bars(name: str) -> pd.DataFrame:
    b = pd.read_csv(FIXTURES / name)
    b["time"] = pd.to_datetime(b["time"], utc=True)
    return b


@pytest.fixture(scope="module")
def gbpusd():
    return _bars("GBPUSDm_H1_2026-01-01_2026-10-30.csv.gz"), _bars("GBPUSDm_M1_2026-10-26_2026-10-30.csv.gz")


def _ny(wall: str) -> datetime:
    return pd.Timestamp(wall, tz=NY).tz_convert("UTC").to_pydatetime()


def test_the_terminal_frames_leave_out_the_forming_day_and_week(gbpusd):
    h1, _ = gbpusd
    m = terminal_market(h1, int(pd.Timestamp(_ny("2026-10-28 10:00")).value))
    assert pd.Timestamp(m.hist["D1"]["date"].iloc[-1]) == pd.Timestamp("2026-10-27")     # Wed 28 is forming
    assert pd.Timestamp(m.hist["W1"]["monday"].iloc[-1]) == pd.Timestamp("2026-10-19")   # so is the week of 26
    assert last_close(_ny("2026-10-28 10:00")) == _ny("2026-10-27 17:00")
    assert last_close(_ny("2026-10-28 17:00")) == _ny("2026-10-28 17:00")


def test_the_week_checks_say_turn_exactly_where_the_reader_finds_one(gbpusd):
    h1, _ = gbpusd
    m = terminal_market(h1, int(pd.Timestamp(_ny("2026-10-30 17:00")).value))
    turns = {(t["t"], t["side"]) for t in reader_turns(m)}
    w1 = m.hist["W1"]
    checks = week_checks(m, n=len(w1))
    closes = dict(zip(w1["monday"].dt.strftime("%Y-%m-%d"), w1["t_close"]))
    said = {(int(closes[c["week"]]), s) for c in checks for s, name in ((1, "BULLISH"), (-1, "BEARISH"))
            if c[name]["turn"]}
    assert said == turns and turns
    oct12 = next(c for c in checks if c["week"] == "2026-10-12")["BULLISH"]
    assert [s[0] for s in oct12["steps"]] == ["soup", "C2 window", "external pool", "D1 CISD"]
    assert oct12["turn"] and "2026 Q2 low" in oct12["steps"][2][2]
    oct19 = next(c for c in checks if c["week"] == "2026-10-19")
    assert not oct19["BULLISH"]["turn"] and not oct19["BEARISH"]["turn"]


def test_the_shadow_week_opens_on_the_traders_narrative_and_reads_thursdays_order(gbpusd):
    h1, m1 = gbpusd
    s = read_market("GBPUSD", h1, m1, date(2026, 10, 26), _ny("2026-10-30 18:00"))
    assert (s["open"]["side"], s["open"]["state"]) == ("BULLISH", "ACTIVE")
    assert s["open"]["draw"]["name"].startswith("W1 gap 07 Sep-21 Sep")
    assert s["now"]["side"] == "BULLISH" and s["as_of"] == _ny("2026-10-30 17:00").isoformat()
    assert s["spans"][-1]["reason"] == "live" and s["spans"][-1]["side"] == "BULLISH"
    reads = {r["day"]: r for r in s["reads"]}
    assert list(reads) == ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
    thu = reads["2026-10-29"]
    assert thu["order"] and thu["verdict"].startswith("ORDER filled 09:18: buy 1.33030")
    assert thu["steps"][0][0] == "narrative" and not thu["so_far"]
    assert reads["2026-10-26"]["verdict"].startswith("NO TRADE") and not reads["2026-10-26"]["order"]


def test_a_day_not_yet_opened_isnt_read_and_the_running_one_is_so_far(gbpusd):
    h1, m1 = gbpusd
    now = _ny("2026-10-28 03:00")
    s = read_market("GBPUSD", h1[h1["time"] < now], m1[m1["time"] < now], date(2026, 10, 26), now)
    assert [r["day"] for r in s["reads"]] == ["2026-10-26", "2026-10-27", "2026-10-28"]
    assert [r["so_far"] for r in s["reads"]] == [False, False, True]


def test_the_shadow_file_keeps_a_market_the_broker_doesnt_carry(gbpusd, tmp_path):
    h1, m1 = gbpusd

    def rates(inst, tf, start, end):
        if inst != "GBPUSD":
            return pd.DataFrame(columns=["time", "open", "high", "low", "close"])
        b = h1 if tf.value == "H1" else m1
        return b[(b["time"] >= pd.Timestamp(start)) & (b["time"] < pd.Timestamp(end))]

    path = write_shadow(date(2026, 10, 26), rates, now=_ny("2026-10-30 18:00"), markets=("GBPUSD", "DXY"),
                        folder=tmp_path / "dis", theses=tmp_path / "dis_theses.json")
    import json
    out = json.loads(path.read_text(encoding="utf-8"))
    rows = {r["market"]: r for r in out["rows"]}
    assert out["week"] == "2026-10-26" and out["source"] == "reader"
    assert rows["GBPUSD"]["open"]["side"] == "BULLISH"
    assert "no H1" in rows["DXY"]["error"]
    # AlgoMindDIS's thesis file (task 397): the side the week opened with, its draw's CE and protected swing
    theses = json.loads((tmp_path / "dis_theses.json").read_text(encoding="utf-8"))
    assert list(theses) == ["GBPUSD"] and list(theses["GBPUSD"]) == [f"2026-10-{d}" for d in range(26, 31)]
    entry = theses["GBPUSD"]["2026-10-29"]
    assert entry == {"side": "BULLISH", "draw": pytest.approx(rows["GBPUSD"]["open"]["draw"]["ce"]),
                     "protected": pytest.approx(1.31364), "since": _ny("2026-10-25 17:00").isoformat(),
                     "source": "reader v0-fe84645"}
    with pytest.raises(LookupError, match="no market read"):     # the terminal down: the week's file stays
        write_shadow(date(2026, 10, 26), lambda *a: None, now=_ny("2026-10-30 18:00"), markets=("GBPUSD",),
                     folder=tmp_path / "dis", theses=tmp_path / "dis_theses.json")
    assert json.loads(path.read_text(encoding="utf-8")) == out


def test_the_thesis_file_holds_only_sides_live_at_the_weeks_open(tmp_path):
    import json

    def record(side, state, draw=None, protected=None):
        return {"side": side, "state": state, "draw": draw, "protected": protected}

    gap = {"name": "D1 gap", "near": 101.0, "far": 103.0, "ce": 102.0}
    (tmp_path / "2026-11-02.json").write_text(json.dumps({"week": "2026-11-02", "source": "reader", "version": "v0",
        "rows": [{"market": "US500", "open": record("BEARISH", "ACTIVE", gap, 110.0)},
                 {"market": "EURUSD", "open": record("NONE", "UNDETERMINED"),
                  "now": record("BEARISH", "ACTIVE", gap, 110.0)},          # set inside the week: not traded
                 {"market": "DXY", "error": "no H1"}]}), encoding="utf-8")
    assert thesis_table(tmp_path) == {"US500": {d: {"side": "BEARISH", "draw": 102.0, "protected": 110.0,
                                                    "since": "2026-11-01T22:00:00+00:00", "source": "reader v0"}
                                                for d in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05",
                                                          "2026-11-06")}}


def test_the_loop_reads_five_minutes_after_each_d1_close_in_new_york_time():
    from algo_mind.__main__ import next_read
    assert next_read(_ny("2026-10-30 16:00")) == _ny("2026-10-30 17:05")
    assert next_read(_ny("2026-10-30 17:05")) == _ny("2026-10-31 17:05")
    assert next_read(_ny("2026-10-31 18:00")) == _ny("2026-11-01 17:05")        # the clocks change that Sunday
    assert next_read(_ny("2026-10-31 18:00")).hour == 22                           # 17:05 EST is 22:05 UTC
