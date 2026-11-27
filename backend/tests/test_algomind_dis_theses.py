"""
Tests for AlgoMindDIS v1's thesis file (algomind-dis task 436): each trading date takes the state at the last D1
close before it opens, nothing later; the broker's D1 is extended with whole M1 days only; the Thesis Engine layer
on Noculus reads the file as its ALGOMIND source.
"""
from __future__ import annotations

import json

import pandas as pd

from algomind_dis import theses as dis_theses


def _ns(text: str) -> int:
    return pd.Timestamp(text, tz="UTC").value


def test_a_date_takes_the_state_at_the_last_close_before_it_opens():
    t = [_ns(f"2026-09-{d} 00:00") for d in (22, 23, 24, 25)]
    rows = pd.DataFrame({"t": t, "state": ["UNDETERMINED", "UNDETERMINED", "BULLISH", "BULLISH"],
                         "draw": [None, None, 1.2, 1.2], "protected": [None, None, 1.1, 1.1],
                         "since": [None, None, t[2], t[2]]})
    got = dis_theses.entries(rows, "2026-09-23", "2026-09-28")
    # Thursday 24 Sep opens Wednesday 17:00 New York (21:00 UTC), before the 24 Sep 00:00 close that set the side
    assert set(got) == {"2026-09-25", "2026-09-28"}
    assert got["2026-09-25"] == {"side": "BULLISH", "draw": 1.2, "protected": 1.1,
                                 "since": "2026-09-24T00:00:00+00:00"}


def test_the_daily_bars_add_only_whole_days_after_the_brokers_last(tmp_path):
    daily, m1 = tmp_path / "d", tmp_path / "m"
    daily.mkdir(), m1.mkdir()
    d1 = pd.DataFrame({"time": pd.to_datetime(["2026-10-21", "2026-10-22"], utc=True), "open": [1.0, 1.1],
                       "high": [1.2, 1.3], "low": [0.9, 1.0], "close": [1.1, 1.2]})
    d1.to_parquet(daily / "EURUSD_D1.parquet", index=False)
    times = pd.date_range("2026-10-22 23:00", "2026-10-24 01:00", freq="h", tz="UTC")
    pd.DataFrame({"time": times, "open": 1.0, "high": 1.5, "low": 0.5, "close": 1.0}).to_parquet(
        m1 / "EURUSD_M1.parquet", index=False)
    got = dis_theses.daily_bars("EURUSD", daily, m1)
    # 23 Oct is whole and added; 24 Oct is the snapshot's last day and may be forming, so it is left out
    assert [str(d.date()) for d in got["date"]] == ["2026-10-21", "2026-10-22", "2026-10-23"]


def test_the_noculus_layer_reads_the_file(tmp_path, monkeypatch):
    from tests.test_backtest_watch import CONFIG, DAY, FixtureSource, TF, UTC, WatchSession, datetime  # noqa: F401
    root = tmp_path
    bars = FixtureSource("EURUSD").bars("EURUSD", TF.M1, datetime(2026, 9, 1, tzinfo=UTC),
                                        datetime(2026, 10, 10, tzinfo=UTC))
    snap = root / "snapshot"
    snap.mkdir()
    frame = pd.DataFrame({"time": [b.timestamp for b in bars], "open": [b.open for b in bars],
                          "high": [b.high for b in bars], "low": [b.low for b in bars],
                          "close": [b.close for b in bars], "volume": [b.volume for b in bars],
                          "spread": [b.spread for b in bars]})
    frame.to_parquet(snap / "EURUSD_M1.parquet", index=False)
    (root / "base.toml").write_text(CONFIG, encoding="utf-8")
    study = root / "config" / "backtests" / "studies" / "watch-test.toml"
    study.parent.mkdir(parents=True)
    study.write_text("holdout_start = 2099-01-01\ncreated_from_data_end = 2099-01-01\n", encoding="utf-8")
    s = WatchSession(root / "base.toml", None, "EURUSD", DAY, 1, snap, studies_root=root)
    s.prepare()
    assert s.state == "ready", s.message
    price = float(frame["close"].iloc[len(frame) // 2])
    path = tmp_path / "algomind.json"
    path.write_text(json.dumps({"EURUSD": {DAY.isoformat(): {
        "side": "BULLISH", "draw": price * 1.02, "protected": price * 0.98,
        "since": pd.Timestamp(s.start).tz_convert("UTC").isoformat()}}}), encoding="utf-8")
    monkeypatch.setattr(dis_theses, "PATH", path)
    got = s.thesis({"t": s.status()["end"], "source": "ALGOMIND", "version": "v1"})
    assert got["source"] == "ALGOMIND" and got["hindsight"] is False and "AlgoMindDIS v1" in got["words"]
    assert got["any"] is True and [x["side"] for x in got["theses"]] == ["BULLISH"]
    monkeypatch.setattr(dis_theses, "PATH", tmp_path / "missing.json")
    s._thesis.clear()
    none = s.thesis({"t": s.status()["end"], "source": "ALGOMIND", "version": "v1"})
    assert none["any"] is False and "no thesis file" in none["words"]
