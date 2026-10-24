"""Model A's entry, against the trader's two (context-engine update 2026-10-23c, Requirement 25, task 363).

Gold, Wednesday 29 January 2025: Model A (H4/M15/M1) framed the trader's short at the previous day's high, saw the
manipulation into it and the displacement, and then missed it. Its entry waits for the OTE after the displacement,
and price broke the new range's low first. The trader got in twice:
- at the level, while C2 ran into it (+5.4R);
- on the retest after the leg extended (+12.4R).

Each entry is replayed on the Model A record (``data/research/model_a_instances.jsonl``, the exploration slice) with
the same costs, horizon and targets. Shorts are described; longs are mirrored.
- **A, the OTE (Model A's own):** its recorded fills, the 0.705 limit after the displacement, stop above C2's extreme.
- **B1, at the level:** once armed, a limit at the POI's near edge, live until C3 closes; stop one spread beyond the
  POI's far edge. **B2:** the same at the POI's midpoint. Only setups with a POI zone (the model and random-POI arms).
- **C, the re-anchored retest:** after a MISSED, track the leg from C2's extreme to the running low, and keep a limit at
  its midpoint until C2's extreme is taken or the day ends; stop one spread beyond C2's extreme.

Each fill is held to the trading day's 17:00 New York close. A short sells at the bid and is closed at the ask (a long
the mirror), so the spread is paid. A minute reaching both the stop and the target is a stop; the fill minute can stop
a trade, not pay it. Targets: a fixed 3R, and Model A's TP1 (C1's opposite extreme) where it lies beyond the fill. The
arms are the controls: ``random_poi_vt`` draws the POI at random, and ``crt`` / ``crt_vt`` read the candles with no
context.

    python -m algo_research.entry_study           # writes docs/research/MODEL_A_ENTRIES.md

Validates: Requirement 25 (.kiro/specs/context-engine/requirements.md)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "data" / "research" / "model_a_instances.jsonl"
SNAPSHOT = REPO / "data" / "research" / "snapshots" / "exness-2025-2026h1"
NY = "America/New_York"
SECONDS = {"M15": 900, "M30": 1800, "H1": 3600}
TARGET_R = 3.0
RESAMPLES = 4000


def wall_minutes(instrument: str) -> dict:
    """The snapshot's M1 in New York wall seconds (the record's clock)."""
    m1 = pd.read_parquet(SNAPSHOT / f"{instrument}_M1.parquet")
    wall = (m1["time"].dt.tz_convert(NY).dt.tz_localize(None) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
    spread = np.maximum(m1["spread"].fillna(0).to_numpy(float), float(m1["spread"].median()))
    return {"time": wall.to_numpy(np.int64), **{k: m1[k].to_numpy(float) for k in ("open", "high", "low", "close")},
            "spread": spread}


class Side:
    """Minutes as a short sees them; a long is mirrored by negating prices. Higher is worse for the trade.

    - ``fill_high``: what a sell limit fills against (a short's bid high; a long's ask low, negated);
    - ``fill_open``: the price a gap fills at;
    - ``stop_high``: what the stop triggers on (a short's ask high; a long's bid low, negated);
    - ``pay_low``: what the target triggers on (a short's ask low; a long's bid high, negated);
    - ``leg_low``: the leg's running extreme as charted (a short's bid low; a long's bid high, negated);
    - ``close``: the exit at the day's end (a short's ask close; a long's bid close, negated).
    """

    def __init__(self, m: dict, short: bool) -> None:
        o, h, l, c, sp = m["open"], m["high"], m["low"], m["close"], m["spread"]
        self.sign = 1.0 if short else -1.0
        if short:
            self.fill_high, self.fill_open, self.stop_high, self.pay_low = h, o, h + sp, l + sp
            self.leg_low, self.close = l, c + sp
        else:
            self.fill_high, self.fill_open, self.stop_high, self.pay_low = -(l + sp), -(o + sp), -l, -h
            self.leg_low, self.close = -h, -c
        self.spread = sp

    def price(self, p: float) -> float:
        return self.sign * p


def race(side: Side, f: int, end: int, fill: float, stop: float, target: float) -> float:
    """R of a short (oriented) filled at minute ``f``: +target R, -1, or the day-end mark."""
    risk = stop - fill
    if risk <= 0 or end <= f:
        return np.nan
    s = np.flatnonzero(side.stop_high[f:end] >= stop)
    t = np.flatnonzero(side.pay_low[f + 1:end] <= target) + 1        # the fill minute can stop it, not pay it
    s0 = s[0] if len(s) else 10**9
    t0 = t[0] if len(t) else 10**9
    if t0 < s0:
        return (fill - target) / risk
    if s0 < 10**9:
        return -1.0
    return (fill - side.close[end - 1]) / risk


def _fill(side: Side, a: int, b: int, limit: float, stop: float) -> Optional[tuple[int, float]]:
    """The first minute in [a, b) a sell limit at ``limit`` fills (at the open on a gap), unless the stop is reached
    first; None if neither."""
    if a >= b:
        return None
    hit = np.flatnonzero(side.fill_high[a:b] >= limit)
    dead = np.flatnonzero(side.stop_high[a:b] >= stop)
    if not len(hit) or (len(dead) and dead[0] < hit[0]):
        return None
    f = a + int(hit[0])
    return f, max(limit, float(side.fill_open[f]))


def _event(r: dict, name: str) -> Optional[int]:
    for e in r["events"]:
        if e[0] == name:
            return int(e[1])
    return None


def trades_of(r: dict, m: dict, sides: dict) -> list[dict]:
    """The entries' trades for one setup of the record."""
    short = r["side"] == "SHORT"
    side = sides[short]
    t = m["time"]
    c_sec = SECONDS[r["c"]]
    armed = _event(r, "ARMED")
    if armed is None:
        return []
    day_end = int(pd.Timestamp(r["trading_date"][:10] + " 17:00").value // 10**9)
    end = int(np.searchsorted(t, day_end, "left"))
    p = side.price
    out = []

    def add(entry: str, f: int, fill: float, stop: float) -> None:
        risk = stop - fill
        if risk <= 0:
            return
        tp1 = p(r["c1_opposite"]) if r.get("c1_opposite") is not None else None
        out.append({"entry": entry, "r3": race(side, f, end, fill, stop, fill - TARGET_R * risk),
                    "rtp1": race(side, f, end, fill, stop, tp1) if tp1 is not None and tp1 < fill else np.nan,
                    "risk": risk})

    # A: Model A's own OTE fill.
    entered = _event(r, "ENTERED")
    if entered is not None and r.get("fill") is not None and r.get("stop") is not None:
        f = int(np.searchsorted(t, entered, "left"))
        if f < end:
            add("A. OTE (Model A)", f, p(r["fill"]), p(r["stop"]))

    # B: a limit at the level once armed, until C3 closes.
    if r.get("poi_near") is not None and r.get("poi_far") is not None:
        near, far = p(r["poi_near"]), p(r["poi_far"])
        a = int(np.searchsorted(t, armed, "left"))
        b = min(end, int(np.searchsorted(t, armed + 2 * c_sec, "left")))
        if a < b and far > near:
            stop = far + float(side.spread[a])
            for entry, limit in (("B1. at the level (near edge)", near), ("B2. inside the level (midpoint)", (near + far) / 2)):
                got = _fill(side, a, b, limit, stop)
                if got is not None:
                    add(entry, got[0], got[1], stop)

    # C: after a MISSED, the leg's midpoint from C2's extreme, re-anchored on the running low.
    missed = _event(r, "MISSED")
    if missed is not None and r.get("c2_extreme") is not None:
        x = p(r["c2_extreme"])
        a = int(np.searchsorted(t, missed, "left"))
        if a < end:
            c2_open = armed
            start = int(np.searchsorted(t, c2_open, "left"))
            low0 = float(np.min(side.leg_low[start:a + 1])) if a + 1 > start else float(side.leg_low[a])
            lows = np.minimum.accumulate(np.r_[low0, side.leg_low[a:end]])[:-1]   # the low before each minute
            limit = lows + 0.5 * (x - lows)
            stop = x + float(side.spread[a])
            hit = np.flatnonzero(side.fill_high[a:end] >= limit)
            dead = np.flatnonzero(side.stop_high[a:end] >= stop)
            if len(hit) and (not len(dead) or hit[0] < dead[0]):
                f = a + int(hit[0])
                add("C. re-anchored retest (0.5)", f, max(float(limit[hit[0]]), float(side.fill_open[f])), stop)
    for row in out:
        row.update(set=r["set"], arm=r["arm"], instrument=r["instrument"], side=r["side"], date=r["trading_date"][:10])
    return out


def collect() -> pd.DataFrame:
    minutes, rows = {}, []
    with open(RECORD, encoding="utf-8") as f:
        for n, line in enumerate(f):
            r = json.loads(line)
            inst = r["instrument"]
            if inst not in minutes:
                m = wall_minutes(inst)
                minutes[inst] = (m, {True: Side(m, True), False: Side(m, False)})
                print("loaded", inst, flush=True)
            m, sides = minutes[inst]
            rows += trades_of(r, m, sides)
            if n % 50000 == 0:
                print(n, len(rows), flush=True)
    return pd.DataFrame(rows)


def _boot(t: pd.DataFrame, col: str, n: int = RESAMPLES, seed: int = 1) -> tuple[float, float]:
    t = t[np.isfinite(t[col])]
    keys = (t["instrument"] + t["date"]).to_numpy()
    uniq, inv = np.unique(keys, return_inverse=True)
    sums, counts = np.bincount(inv, t[col].to_numpy(float)), np.bincount(inv).astype(float)
    w = np.random.default_rng(seed).multinomial(len(uniq), np.full(len(uniq), 1 / len(uniq)), size=n)
    lo, hi = np.percentile((w @ sums) / (w @ counts), [2.5, 97.5])
    return float(lo), float(hi)


def summarize(data: pd.DataFrame) -> str:
    lines = ["# Model A's entry against the trader's two (task 363)", "",
             "The Model A record (exploration slice; EURUSD, GBPUSD, USDJPY, XAUUSD). Every fill is held to the "
             "trading day's 17:00 New York close and pays the spread. R a trade at a fixed 3R target, and at Model A's "
             "TP1 (C1's opposite extreme) where it lies beyond the fill; 95% intervals resample trading dates. The arms "
             "are the controls: `random_poi_vt` draws the POI at random, `crt` reads the candles with no context.", ""]
    for set_name, part in data.groupby("set", sort=False):
        lines += [f"## {set_name}", "", "| Arm | Entry | Fills | Win (3R) | R at 3R | 95% | R at TP1 | 95% |",
                  "|---|---|---|---|---|---|---|---|"]
        for (arm, entry), g in part.groupby(["arm", "entry"], sort=True):
            if len(g) < 20:
                continue
            lo, hi = _boot(g, "r3")
            tp = g[np.isfinite(g["rtp1"])]
            tlo, thi = _boot(tp, "rtp1") if len(tp) >= 20 else (np.nan, np.nan)
            lines.append(f"| {arm} | {entry} | {len(g)} | {(g['r3'] > 0).mean():.0%} | {g['r3'].mean():+.2f} | "
                         f"[{lo:+.2f}, {hi:+.2f}] | {tp['rtp1'].mean():+.2f} | [{tlo:+.2f}, {thi:+.2f}] |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    import sys
    saved = REPO / "data" / "research" / "model_a_entries.parquet"
    if sys.argv[1:] == ["--summary"] and saved.exists():
        data = pd.read_parquet(saved)
    else:
        data = collect()
        data.to_parquet(saved)
    text = summarize(data)
    (REPO / "docs" / "research" / "MODEL_A_ENTRIES.md").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
