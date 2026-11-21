"""The Time Anchor atlas's report (2026-11-21): excess over a random walk by the trader's features, and whether it
holds across time and markets. EXPLORATION on read data: nothing here is a verdict; whatever survives is registered
before it is tested on unread data.

For each current frame and objective, over resolved swings (held or failed; ``po3``: the anchor's close known):
- ``rate`` the share held, ``geo`` the mean random-walk chance, ``excess`` = rate - geo, with a 95% interval
  resampling market-weeks (market-months on D1 and W1);
- one feature at a time, and the trader's story as a composite, fixed before any outcome was read by feature:
  STORY = below the anchor's open, in its first third, in discount of the previous anchor (pd < 0.5), a stack of 2+
  levels, and 2+ opens above in a row. STORY_HTF adds the weighted opens >= 0.5. LOOSE = below the open, first third,
  a stack of 1+.
- cross-validation: before 2024 (A) and from 2024 (B); the three groups (focus, fx, crypto); and the cells ranked on
  A, read on B.

    .venv\\Scripts\\python.exe -m algo_research.atlas.anchor_report
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from algo_research.atlas.anchor import CURRENT, OUT

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "research" / "TIME_ANCHOR_ATLAS.md"
OBJECTIVES = ("anchor", "leg", "crt", "po3")
SPLIT = pd.Timestamp("2024-01-01", tz="UTC").value
RESAMPLES = 2000
MIN_N = 100


def load() -> pd.DataFrame:
    d = pd.concat([pd.read_parquet(p) for p in sorted(OUT.glob("*.parquet"))], ignore_index=True)
    t = pd.to_datetime(d["t_ext"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    coarse = d["tf"].isin(["D1", "W1"])
    d["cluster"] = d["market"] + "|" + np.where(coarse, t.dt.to_period("M").astype(str), t.dt.to_period("W").astype(str))
    d["half"] = np.where(d["t_ext"] < SPLIT, "A", "B")
    d["phase_b"] = pd.cut(d["phase"], [-0.01, 1 / 3, 2 / 3, 1.01], labels=["early", "mid", "late"]).astype(str)
    d["pd_b"] = pd.cut(d["pd"], [-np.inf, 0, 0.5, 1, np.inf], labels=["beyond", "discount", "premium", "above"],
                       right=False).astype(str)
    d["stack_b"] = np.where(d["stack"] >= 2, "2+", d["stack"].astype(str))
    d["stack2_b"] = np.where(d["stack2"] >= 1, "1+", "0")
    d["depth_b"] = np.where(d["depth"] >= 3, "3+", d["depth"].astype(str))
    d["weighted_b"] = np.where(d["weighted"] >= 0.5, "htf>=half", "htf<half")
    d["STORY"] = (d["below_open"] & (d["phase"] < 1 / 3) & (d["pd"] < 0.5) & (d["stack"] >= 2) & (d["depth"] >= 2))
    d["STORY_HTF"] = d["STORY"] & (d["weighted"] >= 0.5)
    d["LOOSE"] = d["below_open"] & (d["phase"] < 1 / 3) & (d["stack"] >= 1)
    return d


def resolved(d: pd.DataFrame, obj: str) -> pd.DataFrame:
    """Rows with a settled outcome: ``y`` 1 held, 0 failed, and ``g`` the random walk's chance."""
    if obj == "po3":
        r = d[d["po3"].notna() & d["geo_po3"].notna()]
        return r.assign(y=r["po3"].astype(bool).astype(float), g=r["geo_po3"].astype(float))
    r = d[d[f"out_{obj}"].isin(["held", "failed"])]
    return r.assign(y=(r[f"out_{obj}"] == "held").astype(float), g=r[f"geo_{obj}"].astype(float))


def excess(r: pd.DataFrame, rng: np.random.Generator) -> dict:
    n = len(r)
    if n == 0:
        return {"n": 0, "rate": np.nan, "geo": np.nan, "excess": np.nan, "lo": np.nan, "hi": np.nan}
    u, inv = np.unique(r["cluster"].to_numpy(), return_inverse=True)
    dy = np.bincount(inv, weights=(r["y"] - r["g"]).to_numpy(), minlength=len(u))
    cnt = np.bincount(inv, minlength=len(u)).astype(float)
    idx = rng.integers(0, len(u), size=(RESAMPLES, len(u)))
    boot = dy[idx].sum(1) / cnt[idx].sum(1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"n": n, "rate": r["y"].mean(), "geo": r["g"].mean(), "excess": r["y"].mean() - r["g"].mean(),
            "lo": lo, "hi": hi}


CELLS = [("below_open", [True, False]), ("phase_b", ["early", "mid", "late"]),
         ("pd_b", ["beyond", "discount", "premium", "above"]), ("stack_b", ["0", "1", "2+"]),
         ("stack2_b", ["0", "1+"]), ("depth_b", ["0", "1", "2", "3+"]), ("weighted_b", ["htf>=half", "htf<half"]),
         ("STORY", [True]), ("STORY_HTF", [True]), ("LOOSE", [True])]


def cell_table(d: pd.DataFrame, seed: int = 20261121) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    for tf in CURRENT:
        for obj in OBJECTIVES:
            r = resolved(d[d["tf"] == tf], obj)
            if r.empty:
                continue
            base = excess(r, rng)
            out.append({"tf": tf, "objective": obj, "feature": "ALL", "value": "", **base, "vs_rest": np.nan})
            for col, values in CELLS:
                for v in values:
                    m = r[col] == v
                    e = excess(r[m], rng)
                    rest = r[~m]
                    e["vs_rest"] = e["excess"] - (rest["y"].mean() - rest["g"].mean()) if len(rest) else np.nan
                    for part, mask in (("A", r["half"] == "A"), ("B", r["half"] == "B")):
                        s = r[m & mask]
                        e[f"excess_{part}"] = s["y"].mean() - s["g"].mean() if len(s) else np.nan
                        e[f"n_{part}"] = len(s)
                    for g in ("focus", "fx", "crypto"):
                        s = r[m & (r["group"] == g)]
                        e[f"excess_{g}"] = s["y"].mean() - s["g"].mean() if len(s) >= 30 else np.nan
                    out.append({"tf": tf, "objective": obj, "feature": col, "value": str(v), **e})
    return pd.DataFrame(out)


def select_on_a(t: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """The cells ranked by their excess on A (n_A >= MIN_N), with what they do on B."""
    c = t[(t["feature"] != "ALL") & (t["n_A"] >= MIN_N) & (t["n_B"] >= MIN_N)].copy()
    c["abs_A"] = c["excess_A"].abs()
    return c.sort_values("abs_A", ascending=False).head(top)


def _p(x) -> str:
    return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{100 * x:+.1f}"


def render(d: pd.DataFrame, t: pd.DataFrame) -> str:
    lines = ["# The Time Anchor atlas (exploration, 2026-11-21)", "",
             "Every three-candle swing on M15, H1, H4, D1 and W1, read through the frame above it (the trader's Time "
             "Anchor) and scored against a driftless random walk from C3's close. Excess = held rate minus the random "
             "walk's chance, in points; the interval resamples market-weeks (market-months on D1 and W1). "
             "Built by `algo_research/atlas/anchor.py`, read by `anchor_report.py`. Data already read: the focus "
             "markets 2021-07 to 2026-11, the eleven FX markets and BTC/ETH/XRP 2021 to 2026. **Exploration: no "
             "verdict.**", "",
             f"Swings: {len(d):,} on {d['market'].nunique()} markets.", ""]
    for tf in CURRENT:
        lines += [f"## {tf} (anchor: the frame above)", "",
                  "| objective | cell | n | rate | geo | excess | 95% | vs rest | A (<2024) | B (2024+) | focus | fx | crypto |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for _, r in t[t["tf"] == tf].iterrows():
            if r["feature"] != "ALL" and r["n"] < 30:
                continue
            cell = "ALL" if r["feature"] == "ALL" else f"{r['feature']} = {r['value']}"
            lines.append(f"| {r['objective']} | {cell} | {int(r['n']):,} | {100 * r['rate']:.1f} | {100 * r['geo']:.1f} | "
                         f"**{_p(r['excess'])}** | [{_p(r['lo'])}, {_p(r['hi'])}] | {_p(r.get('vs_rest'))} | "
                         f"{_p(r.get('excess_A'))} | {_p(r.get('excess_B'))} | {_p(r.get('excess_focus'))} | "
                         f"{_p(r.get('excess_fx'))} | {_p(r.get('excess_crypto'))} |")
        lines.append("")
    s = select_on_a(t)
    lines += ["## Cross-validation: the cells with the largest excess on A, read on B", "",
              "| tf | objective | cell | n A | excess A | n B | excess B | same sign |", "|---|---|---|---|---|---|---|---|"]
    for _, r in s.iterrows():
        same = np.sign(r["excess_A"]) == np.sign(r["excess_B"])
        lines.append(f"| {r['tf']} | {r['objective']} | {r['feature']} = {r['value']} | {int(r['n_A']):,} | "
                     f"{_p(r['excess_A'])} | {int(r['n_B']):,} | {_p(r['excess_B'])} | {'yes' if same else 'NO'} |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    d = load()
    t = cell_table(d)
    t.to_csv(OUT / "cells.csv", index=False)
    DOC.write_text(render(d, t), encoding="utf-8", newline="\n")
    print(f"{len(d):,} swings; wrote {DOC} and {OUT / 'cells.csv'}")


if __name__ == "__main__":
    main()
