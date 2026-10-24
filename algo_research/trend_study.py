"""Does the trader's trend call the next move? (context-engine Requirement 21, task 356)

For each focus market and frame (H1, H4, D1), every closed candle of the exploration slice gets the trend and its
five signals (``algo_research.trend``). The candle's next move is a race on M1 from the next open (MA-D21):
- one average range of the frame (the mean high-low of the 14 candles to and including it) up against one down,
  for up to three candles of the frame;
- a minute reaching both counts against the call;
- unresolved races are counted apart.

A call is right when its side comes first. Its rate is read against 50% and against drift: the same side's rate
over all of the frame's candles in that market. The intervals resample trading dates.

The second outcome reads continuation, since a bearish trend often raids buy-side liquidity before it falls: a call
is right when price trades beyond the last known three-candle swing on its side (a lower low for a bearish call)
before the one on the other side. It is read against geometry, the chance a driftless walk from the next open
reaches that swing first: (high - ref) / (high - low) for the low.

    python -m algo_research.trend_study           # writes docs/research/TRADER_TREND.md

Validates: Requirement 21 (.kiro/specs/context-engine/requirements.md)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from algo_research.atlas.arrays import build_arrays
from algo_research.atlas.report import truncate
from algo_research.config import load_research_config
from algo_research.dataset import build_frames
from algo_research.frame import calendar_columns
from algo_research.snapshot import SNAPSHOTS_DIR, load_snapshot
from algo_research.specs import research_specs
from algo_research.trend import SIGNALS, _swing_highs, _swing_lows, trend_signals
from liquidity_engine.models import Timeframe

REPO = Path(__file__).resolve().parents[1]
FRAMES = (Timeframe.H1, Timeframe.H4, Timeframe.D1)
HORIZON, ATR_BARS = 3, 14
BAR = (0.56, 0.61)                    # the bias a setup needs to clear its costs (task 338)


def _ns(values) -> np.ndarray:
    index = pd.DatetimeIndex(values)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return index.tz_localize(None).to_numpy("datetime64[ns]").view(np.int64)


def races(bars: pd.DataFrame, m1_t: np.ndarray, m1_o: np.ndarray, m1_h: np.ndarray, m1_l: np.ndarray) -> pd.DataFrame:
    """For each closed candle: up_first 1 / 0, both (a minute reaching both), resolved."""
    close = _ns(bars["close_time"])
    rng = (bars["high"] - bars["low"]).to_numpy(float)
    atr = pd.Series(rng).rolling(ATR_BARS).mean().to_numpy()
    n = len(bars)
    up_first = np.full(n, np.nan)
    both = np.zeros(n, bool)
    for i in range(n - 1):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        a = int(np.searchsorted(m1_t, close[i], "left"))
        end_time = close[min(i + HORIZON, n - 1)]
        b = int(np.searchsorted(m1_t, end_time, "left"))
        if a >= b:
            continue
        ref = m1_o[a]
        up = np.flatnonzero(m1_h[a:b] >= ref + atr[i])
        down = np.flatnonzero(m1_l[a:b] <= ref - atr[i])
        u, d = (up[0] if len(up) else np.inf), (down[0] if len(down) else np.inf)
        if u == np.inf and d == np.inf:
            continue
        if u == d:
            both[i] = True
        up_first[i] = 1.0 if u < d else 0.0
    return pd.DataFrame({"up_first": up_first, "both": both})


def _first(values: np.ndarray, start: int, level: float, below: bool) -> int:
    window, i = 256, start
    while i < len(values):
        hit = np.flatnonzero(values[i:i + window] < level if below else values[i:i + window] > level)
        if len(hit):
            return i + int(hit[0])
        i += window
        window *= 2
    return -1


def continuation(bars: pd.DataFrame, m1_t: np.ndarray, m1_o: np.ndarray, m1_h: np.ndarray,
                 m1_l: np.ndarray) -> pd.DataFrame:
    """For each closed candle: low_first (the last swing low traded below before the last swing high is traded above;
    a minute doing both counts as the high first) and geo_low, a driftless walk's chance of the same."""
    h, l = bars["high"].to_numpy(float), bars["low"].to_numpy(float)
    close = _ns(bars["close_time"])
    highs, lows = _swing_highs(h), _swing_lows(l)
    n = len(bars)
    low_first, geo = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        kh = highs[: np.searchsorted(highs + 1, i, "right")]
        kl = lows[: np.searchsorted(lows + 1, i, "right")]
        a = int(np.searchsorted(m1_t, close[i], "left"))
        if not len(kh) or not len(kl) or a >= len(m1_t):
            continue
        top, bottom, ref = h[kh[-1]], l[kl[-1]], m1_o[a]
        if not bottom < ref < top:
            continue
        up, down = _first(m1_h, a, top, below=False), _first(m1_l, a, bottom, below=True)
        if up < 0 and down < 0:
            continue
        low_first[i] = 1.0 if (down >= 0 and (up < 0 or down < up)) else 0.0
        geo[i] = (top - ref) / (top - bottom)
    return pd.DataFrame({"low_first": low_first, "geo_low": geo})


def _calls(table: pd.DataFrame, column: str) -> pd.DataFrame:
    """The rows where ``column`` names a side: right (its side first, a both-minute counting against), and the
    drift base of that side in the same market and frame."""
    t = table[table["up_first"].notna() & (table[column] != 0)].copy()
    up = t[column] > 0
    t["right"] = np.where(up, (t["up_first"] == 1) & ~t["both"], (t["up_first"] == 0) & ~t["both"]).astype(float)
    t["base"] = np.where(up, t["base_up"], t["base_down"])
    return t


def _boot(t: pd.DataFrame, value: str, n: int = 4000, seed: int = 1) -> tuple[float, float]:
    keys = (t["instrument"] + t["date"].astype(str)).to_numpy()
    uniq, inv = np.unique(keys, return_inverse=True)
    sums, counts = np.bincount(inv, t[value].to_numpy(float)), np.bincount(inv).astype(float)
    w = np.random.default_rng(seed).multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)), size=n)
    lo, hi = np.percentile((w @ sums) / (w @ counts), [2.5, 97.5])
    return float(lo), float(hi)


def collect() -> pd.DataFrame:
    cfg = load_research_config()
    since, until = cfg.slice_period("explore")
    snapshot = load_snapshot(SNAPSHOTS_DIR / cfg.snapshot, cfg.instruments)
    frames = build_frames(snapshot, research_specs(cfg))
    rows = []
    for inst in cfg.instruments:
        frame = truncate(frames[inst], until)
        arrays = build_arrays(frame, FRAMES)
        a = frame.arrays
        for tf in FRAMES:
            bars = frame.bars[tf].reset_index(drop=True)
            signals = trend_signals(bars, arrays[arrays["tf"] == tf.value].reset_index(drop=True))
            outcome = races(bars, a["time"], a["open"], a["high"], a["low"])
            cont = continuation(bars, a["time"], a["open"], a["high"], a["low"])
            table = pd.concat([bars[["close_time"]], signals, outcome, cont], axis=1)
            table = table[(table["close_time"] >= pd.Timestamp(since)) & (table["close_time"] < pd.Timestamp(until))]
            resolved = table["up_first"].notna()
            table["base_up"] = ((table.loc[resolved, "up_first"] == 1) & ~table.loc[resolved, "both"]).mean()
            table["base_down"] = ((table.loc[resolved, "up_first"] == 0) & ~table.loc[resolved, "both"]).mean()
            table["date"] = calendar_columns(pd.DatetimeIndex(table["close_time"]))["trading_date"].to_numpy()
            table["instrument"], table["tf"] = inst, tf.value
            rows.append(table)
        print(inst, flush=True)
    return pd.concat(rows, ignore_index=True)


def summarize(data: pd.DataFrame) -> str:
    lines = ["# The trader's trend: does it call the next move? (task 356)", "",
             "Exploration slice, the focus markets. For each closed candle of the frame, a race on M1 from the next "
             "open: one average range of the frame up against one down, for up to three candles. A call is right "
             "when its side comes first (a minute reaching both counts against it). **Excess** is the rate minus the "
             "same side's rate over all candles of that market and frame (drift). Intervals resample trading dates. "
             f"The bar a bias needs to clear the trader's costs: {BAR[0]:.0%}-{BAR[1]:.0%} (task 338).", ""]
    for tf, part in data.groupby("tf", sort=False):
        lines += [f"## {tf}", "", "| Call | n | Right | 95% | Excess over drift | 95% | Unresolved |",
                  "|---|---|---|---|---|---|---|"]
        for column in ("trend",) + SIGNALS:
            t = _calls(part, column)
            if len(t) < 30:
                lines.append(f"| {column} | {len(t)} | | | | | |")
                continue
            t["excess"] = t["right"] - t["base"]
            lo, hi = _boot(t, "right")
            elo, ehi = _boot(t, "excess")
            unresolved = 1 - part[part[column] != 0]["up_first"].notna().mean()
            lines.append(f"| {column} | {len(t)} | {t['right'].mean():.1%} | [{lo:.1%}, {hi:.1%}] | "
                         f"{100 * t['excess'].mean():+.1f} pts | [{100 * elo:+.1f}, {100 * ehi:+.1f}] | {unresolved:.0%} |")
        t = _calls(part, "trend")
        lines += ["", "By market, the trend:", "", "| Market | n | Right | Excess |", "|---|---|---|---|"]
        for inst, g in t.groupby("instrument", sort=False):
            lines.append(f"| {inst} | {len(g)} | {g['right'].mean():.0%} | {100 * (g['right'] - g['base']).mean():+.1f} pts |")
        share = (part["trend"] != 0).mean()
        lines += ["", f"The trend named a side on {share:.0%} of the {tf} candles.", "",
                  "Continuation (the call's side's last swing taken first), against geometry:", "",
                  "| Call | n | Right | Geometry | Excess | 95% |", "|---|---|---|---|---|---|"]
        for column in ("trend",) + SIGNALS:
            t = part[part["low_first"].notna() & (part[column] != 0)].copy()
            if len(t) < 30:
                continue
            bear = t[column] < 0
            t["right"] = np.where(bear, t["low_first"], 1 - t["low_first"])
            t["geo"] = np.where(bear, t["geo_low"], 1 - t["geo_low"])
            t["excess"] = t["right"] - t["geo"]
            lo, hi = _boot(t, "excess")
            lines.append(f"| {column} | {len(t)} | {t['right'].mean():.1%} | {t['geo'].mean():.1%} | "
                         f"{100 * t['excess'].mean():+.1f} pts | [{100 * lo:+.1f}, {100 * hi:+.1f}] |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    data = collect()
    data.to_parquet(REPO / "data" / "research" / "trader_trend.parquet")
    text = summarize(data)
    (REPO / "docs" / "research" / "TRADER_TREND.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
