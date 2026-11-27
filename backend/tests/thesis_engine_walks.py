"""Random-walk M1 markets for the Thesis Engine's tests (not a test module)."""
from __future__ import annotations

import numpy as np
import pandas as pd

NY = "America/New_York"


def walk_m1(weeks: int, seed: int, start: str = "2022-01-02 17:00", spread: float = 0.0001,
            step: float = 0.00012) -> pd.DataFrame:
    """``weeks`` FX weeks of one-minute bars (Sunday 17:00 to Friday 17:00 New York), a random walk with dojis."""
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp(start, tz=NY)
    times = pd.DatetimeIndex(np.concatenate([
        pd.date_range(t0 + pd.Timedelta(weeks=w), periods=5 * 1440, freq="1min").tz_convert("UTC").asi8
        for w in range(weeks)])).tz_localize("UTC")
    n = len(times)
    drift = np.repeat(rng.normal(0, step * 0.15, n // 240 + 1), 240)[:n]       # slow swings, so frames trend
    c = 1.1 + np.cumsum(rng.normal(0, step, n) + drift)
    o = np.r_[1.1, c[:-1]] + rng.normal(0, step * 0.1, n)
    doji = rng.random(n) < 0.03
    c[doji] = o[doji]
    h = np.maximum(o, c) + np.abs(rng.normal(0, step * 0.6, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, step * 0.6, n))
    return pd.DataFrame({"time": times, "open": o, "high": h, "low": l, "close": c, "spread": spread})


def mirrored(m1: pd.DataFrame) -> pd.DataFrame:
    """The same bars upside down: a low becomes a high, an up candle a down one."""
    return m1.assign(open=-m1["open"], high=-m1["low"], low=-m1["high"], close=-m1["close"])
