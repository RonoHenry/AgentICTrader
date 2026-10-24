"""Does ranking the swings, or reading breaks instead of swings, make structure call the next day?
(context-engine Requirement 24, task 359)

The trader's structure signal (task 355) compares the last two three-candle swings and, with the four other signals,
called the next move no better than a coin (task 356). Two changes are tried, from ICT's own definitions:
- **ranked swings:** intermediate-term highs and lows (an STH higher than the STH on either side, known once the next
  STH has formed) instead of short-term ones;
- **breaks, not sweeps:** the state flips only when a candle closes beyond the latest unbroken swing; a wick through
  it that closes back inside changes nothing. Optionally the breaking candle must leave an FVG.

Each version's state at the 17:00 New York close (D1, and the H4 candle closing then) calls the next D1 candle: right
when it closes the called way. The rate is read against 50% and against drift (the market's share of days closing that
way in the slice), with a trading-date bootstrap. The same is read with each version swapped into the five-signal
trend score. The bar is the earlier mechanical reads' 45-49% on the next day (task 338), and 56-61% to pay.

    python -m algo_research.structure_study          # writes docs/research/TREND_STRUCTURE.md

Validates: Requirement 24 (.kiro/specs/context-engine/requirements.md)
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
from algo_research.trend import TREND_AT, break_state, compare_state, trend_signals
from liquidity_engine.models import Timeframe

REPO = Path(__file__).resolve().parents[1]
FRAMES = (Timeframe.D1, Timeframe.H4)
VERSIONS = {
    "A. STH compare (task 355)": lambda o, h, l, c: compare_state(h, l, "STH"),
    "B. ITH compare": lambda o, h, l, c: compare_state(h, l, "ITH"),
    "C. STH break": lambda o, h, l, c: break_state(o, h, l, c, "STH"),
    "D. ITH break": lambda o, h, l, c: break_state(o, h, l, c, "ITH"),
    "E. ITH break + FVG": lambda o, h, l, c: break_state(o, h, l, c, "ITH", fvg=True),
}


def _boot(df: pd.DataFrame, col: str, n: int = 4000, seed: int = 1) -> tuple[float, float]:
    dates = df["date"].astype(str).to_numpy()
    uniq, inv = np.unique(dates, return_inverse=True)
    sums, counts = np.bincount(inv, df[col].to_numpy(float)), np.bincount(inv).astype(float)
    w = np.random.default_rng(seed).multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)), size=n)
    lo, hi = np.percentile((w @ sums) / (w @ counts), [2.5, 97.5])
    return float(lo), float(hi)


def collect() -> pd.DataFrame:
    """One row per market and D1 close: each version's call on D1 and H4, the swapped trend scores, and the next
    D1 candle's direction (+1, -1, 0 for a doji)."""
    cfg = load_research_config()
    end = cfg.slice_period("confirm")[1]
    frames = build_frames(load_snapshot(SNAPSHOTS_DIR / cfg.snapshot, cfg.instruments), research_specs(cfg))
    rows = []
    for inst in cfg.instruments:
        frame = truncate(frames[inst], end)
        arrays = build_arrays(frame, FRAMES)
        d1 = frame.bars[Timeframe.D1].reset_index(drop=True)
        nxt = np.sign(d1["close"].to_numpy(float) - d1["open"].to_numpy(float))
        table = pd.DataFrame({"close_time": d1["close_time"], "next": np.r_[nxt[1:], np.nan]})
        for tf in FRAMES:
            bars = frame.bars[tf].reset_index(drop=True)
            o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
            signals = trend_signals(bars, arrays[arrays["tf"] == tf.value].reset_index(drop=True))
            states = {name: f(o, h, l, c) for name, f in VERSIONS.items()}
            # Each D1 close reads the frame's last candle closed by then.
            at = np.searchsorted(pd.DatetimeIndex(bars["close_time"]).asi8,
                                 pd.DatetimeIndex(table["close_time"]).asi8, "right") - 1
            ok = at >= 0
            for name, state in states.items():
                table[f"{tf.value}|{name}"] = np.where(ok, state[np.maximum(at, 0)], 0)
                score = signals["score"].to_numpy() - signals["structure"].to_numpy() + state
                trend = np.where(score <= -TREND_AT, -1, np.where(score >= TREND_AT, 1, 0))
                table[f"{tf.value}|trend with {name[:2]}"] = np.where(ok, trend[np.maximum(at, 0)], 0)
        table["date"] = calendar_columns(pd.DatetimeIndex(table["close_time"]))["trading_date"].to_numpy()
        table["instrument"] = inst
        rows.append(table)
        print(inst, flush=True)
    return pd.concat(rows, ignore_index=True)


def summarize(data: pd.DataFrame) -> str:
    cfg = load_research_config()
    lines = ["# Ranked swings and breaks: does structure call the next day? (task 359)", "",
             "Each version's state at the 17:00 New York close, on D1 and on the H4 candle closing then, calls the "
             "next D1 candle. **Right** is the share of calls whose next day closed that way (dojis left out); "
             "**excess** is that minus the market's share of days closing the called way in the slice (drift). "
             "Intervals resample trading dates. Earlier mechanical reads called the day 45-49% (task 338); a bias "
             "needs 56-61% to pay. The ten focus markets.", ""]
    calls = [c for c in data.columns if "|" in c]
    for slice_name in ("explore", "confirm"):
        first, end = cfg.slice_period(slice_name)
        part = data[(data["close_time"] >= pd.Timestamp(first)) & (data["close_time"] < pd.Timestamp(end))
                    & data["next"].notna() & (data["next"] != 0)].copy()
        up = part.groupby("instrument")["next"].apply(lambda s: (s > 0).mean())
        a, b = getattr(cfg.slices, slice_name)
        lines += [f"## {slice_name} slice ({a:%Y-%m-%d} to {b:%Y-%m-%d})", "",
                  "| Frame | Call | n | Right | 95% | Excess over drift | 95% |", "|---|---|---|---|---|---|---|"]
        for col in calls:
            t = part[part[col] != 0].copy()
            if len(t) < 30:
                continue
            t["right"] = (np.sign(t[col]) == t["next"]).astype(float)
            base_up = t["instrument"].map(up)
            t["excess"] = t["right"] - np.where(t[col] > 0, base_up, 1 - base_up)
            lo, hi = _boot(t, "right")
            elo, ehi = _boot(t, "excess")
            tf, name = col.split("|")
            lines.append(f"| {tf} | {name} | {len(t)} | {t['right'].mean():.1%} | [{lo:.1%}, {hi:.1%}] | "
                         f"{100 * t['excess'].mean():+.1f} pts | [{100 * elo:+.1f}, {100 * ehi:+.1f}] |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    import sys
    saved = REPO / "data" / "research" / "trend_structure.parquet"
    if sys.argv[1:] == ["--summary"] and saved.exists():          # re-summarize without recomputing
        data = pd.read_parquet(saved)
    else:
        data = collect()
        data.to_parquet(saved)
    text = summarize(data)
    (REPO / "docs" / "research" / "TREND_STRUCTURE.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
