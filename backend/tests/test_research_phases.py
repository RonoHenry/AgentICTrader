"""
The phase of price delivery (liquidity-engine Requirement 28.1, task 345).

ICT's cycle: consolidation -> expansion -> retracement -> reversal -> consolidation. Read candle by candle with the
engine's CRT thresholds: 8 candles within 2 average ranges (of the 14 candles before them) are a consolidation; the
close that leaves its box is the expansion, its leg from the box's opposite extreme; a candle that makes no new
extreme in the leg is a retracement; a close beyond the leg's origin is a reversal.
"""
from __future__ import annotations

import numpy as np

from algo_research.phases import episodes, label_phases


def series(rows):
    """(open, high, low, close) arrays from rows of four prices."""
    a = np.asarray(rows, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def noisy(n: int, start: float = 100.0, width: float = 1.0) -> list[tuple]:
    """n candles of range ``width`` drifting up by width each: an average true range of about 2 x width."""
    rows, price = [], start
    for _ in range(n):
        rows.append((price, price + width, price - width, price + width * 0.8))
        price += width
    return rows


def tight(n: int, mid: float, half: float = 0.4) -> list[tuple]:
    """n small candles around ``mid``: together within one unit."""
    return [(mid, mid + half, mid - half, mid + (0.1 if i % 2 else -0.1)) for i in range(n)]


def test_eight_tight_candles_open_a_consolidation_and_a_close_outside_ends_it_in_an_expansion():
    rows = noisy(22) + tight(8, 125.0) + [(125.0, 125.6, 124.6, 125.1)]      # still inside its box
    rows += [(125.1, 128.0, 125.0, 127.8)]                                   # a close above the box
    o, h, l, c = series(rows)
    labels = label_phases(o, h, l, c)
    assert labels[29] == "consolidation" and labels[30] == "consolidation"   # the 8th tight candle on
    assert labels[31] == "expansion"
    ep = episodes(o, h, l, c, np.arange(len(rows)))
    last = ep.iloc[-1]
    assert last["direction"] == 1 and last["broken_at"] == 31
    assert last["box_high"] == 125.4 and last["box_low"] == 124.6
    assert last["origin"] == 124.6                                          # the box's opposite extreme


def test_a_wick_beyond_the_box_that_closes_inside_is_the_manipulation():
    rows = noisy(22) + tight(8, 125.0)
    rows += [(125.0, 125.1, 123.9, 124.9)]                                   # a wick below, back inside
    rows += [(124.9, 125.2, 124.7, 125.0), (125.0, 128.0, 124.9, 127.8)]    # then the break up
    o, h, l, c = series(rows)
    ep = episodes(o, h, l, c, np.arange(len(rows)))
    last = ep.iloc[-1]
    assert last["manipulation"] == "low" and last["manipulated_at"] == 30
    assert last["direction"] == 1 and last["origin"] == 123.9                # the leg starts at the wick
    assert label_phases(o, h, l, c)[30] == "consolidation"


def test_after_an_expansion_a_candle_without_a_new_extreme_is_a_retracement_and_beyond_the_origin_a_reversal():
    rows = noisy(22) + tight(8, 125.0) + [(125.0, 128.0, 124.9, 127.8)]     # expansion up, origin 124.6
    rows += [(127.8, 129.0, 127.5, 128.8)]                                   # a new high: still expansion
    rows += [(128.8, 128.9, 126.0, 126.2)]                                   # no new high: retracement
    rows += [(126.2, 126.3, 123.5, 123.8)]                                   # a close below 124.6: reversal
    o, h, l, c = series(rows)
    labels = label_phases(o, h, l, c)
    assert list(labels[30:]) == ["expansion", "expansion", "retracement", "reversal"]


def test_nothing_after_a_candle_changes_its_label():
    rng = np.random.default_rng(3)
    steps = rng.normal(0, 1, 400).cumsum() + 100
    o = steps
    c = steps + rng.normal(0, 0.5, 400)
    h = np.maximum(o, c) + rng.uniform(0, 1, 400)
    l = np.minimum(o, c) - rng.uniform(0, 1, 400)
    full = label_phases(o, h, l, c)
    for cut in (60, 150, 299, 399):
        assert list(label_phases(o[:cut], h[:cut], l[:cut], c[:cut])) == list(full[:cut])
