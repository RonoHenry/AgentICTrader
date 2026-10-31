"""
Tests for algo_research/sequence.py — the trader's sequence, v0 (context-engine Requirement 33).

The acceptance test is the trader's own trade: their Backtest Diary for GBPUSD, Thursday 29 Oct 2026, on Exness
bars (fixtures/research/sequence: H1 for 2026, M1 for 26-30 Oct). Reading only the candles closed at each step,
the reader must find their narrative, their D1 soup and the arrays they named, their CISD runs, their order block,
their stop and their target. The mirror test reads the same bars upside down: a sell read is the buy read's mirror.
The rest pin the soup and the CISD on hand-made candles.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from algo_research.sequence import cisd, read_day, soups

FIXTURES = Path(__file__).parent / "fixtures" / "research" / "sequence"
THURSDAY = date(2026, 10, 29)


def _bars(name: str) -> pd.DataFrame:
    b = pd.read_csv(FIXTURES / name)
    b["time"] = pd.to_datetime(b["time"], utc=True)
    return b


def _flip(b: pd.DataFrame) -> pd.DataFrame:
    return b.assign(open=-b["open"], high=-b["low"], low=-b["high"], close=-b["close"])


@pytest.fixture(scope="module")
def gbpusd():
    return _bars("GBPUSDm_H1_2026-01-01_2026-10-30.csv.gz"), _bars("GBPUSDm_M1_2026-10-26_2026-10-30.csv.gz")


def test_the_reader_finds_the_traders_gbpusd_long_of_29_oct_2026(gbpusd):
    read = read_day("GBPUSDm", *gbpusd, THURSDAY)
    text, f = read.render(), read.facts
    assert read.side == 1
    # the narrative: the W1 soup that took the Q2 low (ERL), drawn to the September W1 gap (IRL)
    assert "C2 week 12 Oct took the 2026 Q2 low 1.31395 (low 1.31364)" in text
    assert "draw: W1 gap 07 Sep-21 Sep 1.33998-1.34803 (CE 1.34401)" in text
    # the setup: the Tuesday-Wednesday soup into the arrays the trader named, the H4 and H1 runs they wrote down
    assert "C1 Tue 27 Oct (low 1.33023), C2 Wed 28 Oct low 1.32720 at Wed 03:17" in text
    assert "D1 +IFVG 22 Sep-24 Sep 1.32555-1.33207" in text and "NDOG 16 Oct 1.32697-1.32759" in text
    assert "H4 run from Tue 21:00 (open 1.33048)" in text and "H1 run from Tue 23:00 (open 1.33038)" in text
    # C3: Asia's range, London's Judas swing, the M5 CISD and its order block
    assert f["q1"] == pytest.approx((1.33022, 1.33355))
    assert f["sweep"] == pd.Timestamp("2026-10-29 05:20")
    assert f["judas"] == pytest.approx((1.33172, 1.32956))
    assert (f["judas_high_at"], f["low_at"]) == (pd.Timestamp("2026-10-29 04:55"), pd.Timestamp("2026-10-29 05:27"))
    start, level, confirm = f["cisd"]
    assert (start, confirm) == (pd.Timestamp("2026-10-29 05:05"), pd.Timestamp("2026-10-29 06:00"))
    assert level == pytest.approx(1.33128)
    assert (f["entry"], f["stop"]) == (pytest.approx(1.33030), pytest.approx(1.32956))
    assert f["fill"] == pd.Timestamp("2026-10-29 09:18") and f["stopped"] is None
    # the targets: -1 at the PDH, -4 at the draw's edge (the trader's 1.34003 on their chart)
    dev = {t["dev"]: t for t in f["targets"]}
    assert "PDH" in [n for n, _ in dev[1.0]["near"]]
    assert f["draw_dev"] == 4.0 and dev[4.0]["hit"] is not None
    assert read.verdict.startswith("ORDER filled 09:18")


def test_in_the_fixtures_week_it_orders_only_on_the_traders_day(gbpusd):
    days = (date(2026, 10, 27), date(2026, 10, 28), THURSDAY, date(2026, 10, 30))
    verdicts = {d: read_day("GBPUSDm", *gbpusd, d).verdict for d in days}
    assert [d for d, v in verdicts.items() if v.startswith("ORDER")] == [THURSDAY]
    assert all("no D1 soup" in v for d, v in verdicts.items() if d != THURSDAY)


def test_a_sell_read_is_the_mirror_of_the_buy_read(gbpusd):
    history, m1 = gbpusd
    buy = read_day("X", history, m1, THURSDAY)
    sell = read_day("X", _flip(history), _flip(m1), THURSDAY)
    assert sell.side == -1
    for key in ("q1", "judas", "entry", "stop"):
        assert np.allclose(sell.facts[key], -np.asarray(buy.facts[key]))
    for key in ("sweep", "fill", "low_at", "judas_high_at", "draw_dev"):
        assert sell.facts[key] == buy.facts[key]
    assert "BEARISH" in sell.render() and "sell limit" in sell.render()


def _frame(rows) -> pd.DataFrame:
    """Candles from (open, high, low, close) rows, an hour apart."""
    t = np.arange(len(rows), dtype=np.int64) * 3_600 * 10**9
    o, h, l, c = (np.array(x, dtype=float) for x in zip(*rows))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "t_open": t, "t_close": t + 3_600 * 10**9})


def test_a_soup_is_two_candles_c2_under_c1s_low_and_closing_back_above_it():
    b = _frame([(10.0, 11.0, 9.0, 10.0),
                (10.0, 10.5, 8.5, 9.5),     # under C1's low, back above it: a soup
                (9.5, 10.0, 8.0, 8.2),      # under, but closes below it: none
                (8.2, 9.0, 8.1, 8.8)])      # doesn't take the low: none
    assert soups(b).tolist() == [1]


def test_the_cisd_run_starts_after_an_up_candle_or_a_doji_and_confirms_on_a_close_above_its_open():
    b = _frame([(10.0, 10.2, 9.9, 10.1),     # up: ends the run
                (10.1, 10.15, 9.6, 10.09),   # a doji (a body of 0.01 in a 0.55 range): ends it too
                (10.09, 10.1, 9.7, 9.8),     # down: the run's first candle, its open the level
                (9.8, 9.85, 9.3, 9.4),       # down: the run's last candle (the order block)
                (9.4, 9.6, 9.0, 9.5),        # the low, closing up: not in the run
                (9.5, 10.0, 9.45, 10.0),     # closes under 10.09: not yet
                (10.0, 10.3, 9.95, 10.2)])   # closes above it: the CISD
    shift = cisd(b, 4, until=int(b["t_close"].iloc[-1]))
    assert (shift["start"], shift["end"], shift["level"], shift["confirm"]) == (2, 3, 10.09, 6)
    assert cisd(b, 4, until=int(b["t_close"].iloc[5]))["confirm"] == -1
