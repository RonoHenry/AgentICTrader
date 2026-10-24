"""
Tests for algo_research/chain_view.py — the chain and the stack read for Noculus's Chain layer (2026-10-24).

The chart must show exactly what the study read: on the chain tests' wave, every vote, score and call at a close
equals ``search_stack.stack_votes`` (SMT abstaining), and the frames and links are the chain's. The chart's 17:00
New York candles are labelled with their trading date, and everything serialises for the page.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from algo_research.chain_view import ChainView, trading_days
from algo_research.search_stack import VOTES, stack_votes
from algo_backtester.watch import wall
from tests.test_research_search_chain import bars_on


@pytest.fixture(scope="module")
def wave():
    b = bars_on(pd.bdate_range("2019-01-01", periods=420, tz="UTC"), seed=4)
    return b, ChainView(b.assign(open_wall=np.arange(len(b)) * 86400)), stack_votes(b)


def test_the_chart_reads_what_the_study_read(wave):
    _, view, study = wave
    called = np.flatnonzero(study["H-M"].to_numpy() != 0)
    sample = sorted(set(range(0, 420, 23)) | set(called[:5].tolist()) | set(np.flatnonzero(study["H-K"] != 0)[:5]))
    for i in sample:
        row = view.at(i)
        assert row["votes"] == {k: int(study[k].iloc[i]) for k in VOTES}, i
        assert (row["score"], row["call"], row["ranged"]) == (int(study["score"].iloc[i]), int(study["H-M"].iloc[i]),
                                                               bool(study["ranged"].iloc[i])), i
        assert row["chain_call"] == int(study["H-K"].iloc[i])
    assert any(view.at(i)["call"] != 0 for i in called[:3])


def test_frames_and_links_are_the_chains(wave):
    _, view, study = wave
    i = int(np.flatnonzero(study["H-K"] != 0)[0])
    row = view.at(i)
    assert [f["tf"] for f in row["frames"]] == ["MN1", "W1", "D1"] == [x["tf"] for x in row["links"]]
    assert row["links"][-1]["context"] == ("BULLISH" if row["chain_call"] > 0 else "BEARISH")
    for f in row["frames"]:
        low, high = f["range"]
        assert low < high and set(f["reasons"]) >= {"range", "zone", "poi_bullish", "poi_bearish"}
    json.dumps(row)                                                   # the page reads it as it is


def test_no_frames_until_weeks_and_months_close(wave):
    _, view, _ = wave
    early = view.at(3)
    assert early["frames"] == [] and early["call"] == 0 and early["chain_call"] == 0 and not early["ranged"]


def test_the_chart_s_candles_are_labelled_by_their_trading_date():
    opens = [wall(pd.Timestamp(t, tz="America/New_York")) for t in ("2025-01-05 17:00", "2025-01-06 17:00",
                                                                      "2025-01-09 17:00")]
    rows = pd.DataFrame({"time": opens, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05})
    days = trading_days(rows)
    assert list(days["time"].dt.strftime("%a %Y-%m-%d")) == ["Mon 2025-01-06", "Tue 2025-01-07", "Fri 2025-01-10"]
    assert list(days["open_wall"]) == opens
