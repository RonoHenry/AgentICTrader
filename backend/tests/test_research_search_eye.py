"""
Tests for algo_research/search_eye.py — H-AB, the eye's chart pictures (docs/research/SEARCH_2018_2024.md).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algo_research.search_eye import DAYS, HEIGHT, WIDTH, _network, images, samples, week_pictures


def days(n=80, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 + rng.normal(0, 1, n).cumsum()
    o = c + rng.normal(0, 0.4, n)
    return pd.DataFrame({"date": pd.bdate_range("2017-01-02", periods=n), "open": o,
                         "high": np.maximum(o, c) + 0.5, "low": np.minimum(o, c) - 0.5, "close": c})


def test_a_picture_draws_each_days_open_bar_and_close_in_three_columns():
    o = np.array([[10.0] * DAYS]); h = np.array([[12.0] * DAYS]); l = np.array([[8.0] * DAYS])
    c = np.array([[11.0] * DAYS]); ma = np.full((1, DAYS), 10.0)
    img = images(o, h, l, c, ma)[0]
    assert img.shape == (HEIGHT, WIDTH) and set(np.unique(img)) <= {0, 255}
    row = lambda p: int(round((12 - p) / 4 * (HEIGHT - 1)))                      # noqa: E731
    assert img[:, 1].sum() == 255 * HEIGHT                                       # the bar spans the window
    assert img[row(11.0), 2] == 255 and img[row(10.0), 0] == 255                 # close tick right, open tick left
    assert img[row(10.0), 4] == 255                                              # the average's line between bars


def test_training_samples_stop_before_the_fit_end_and_week_pictures_use_only_earlier_days():
    d = days(400)
    x, y, dt = samples("X", d)
    assert x.shape[1:] == (HEIGHT, WIDTH) and len(x) == len(y) == len(dt) and set(np.unique(y)) <= {0.0, 1.0}
    assert (dt >= d["date"].to_numpy("datetime64[ns]")[2 * DAYS - 2]).all()
    weeks = pd.Series(pd.to_datetime(["2017-01-09", "2017-06-05"]))
    img, ok = week_pictures("X", d, weeks)
    assert ok.tolist() == [False, True] and img.shape == (1, HEIGHT, WIDTH)
    before = d[d["date"] < "2017-06-05"].tail(DAYS)
    from algo_research.search_eye import pictures
    assert (pictures(d, np.array([before.index[-1]])) == img).all()


def test_the_network_reads_a_picture_into_one_logit():
    import torch
    out = _network()(torch.zeros(3, 1, HEIGHT, WIDTH))
    assert out.shape == (3,)
