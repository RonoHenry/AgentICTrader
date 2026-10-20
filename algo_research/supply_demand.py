"""Supply and demand zones, and the first return to each as a trade (algo-research update 2026-10-20).

The trader asked (2026-10-20) to pair supply and demand with what is already built. This is the classic reading,
written down before any result was seen:

- **A zone** is a base and a leg-out on one timeframe:
  - **the base:** 1 to 3 consecutive candles whose bodies are at most half their range (``BASE_BODY``);
  - **the leg-out:** the next candle, explosive: a body of at least 60% of its range (``OUT_BODY``), a range of at
    least 1.5 times the average range of the 20 candles before it (``OUT_RANGE``), closing beyond the base.
- **Demand or supply.** A leg-out closing above the base makes demand (drop-base-rally, rally-base-rally); one
  closing below makes supply (rally-base-drop, drop-base-drop).
- **Its lines.** The proximal line is the base's body edge nearest price; the distal line is the far wick of the
  base and the leg-out.
- **When it is known:** at the leg-out's close.
- **Fresh** until price first trades back to the proximal line (``first_touch``). Broken by the first close beyond
  the distal line (``broken``).
- **The trade:** a limit at the proximal line from the leg-out's close (so it fills on the first return), the stop
  beyond the distal line by ``STOP_BUFFER`` of the zone's height, and a fixed 2R or 3R target. It expires after
  ``EXPIRY`` candles of the zone's timeframe, and once filled is held ``HOLD`` candles at most.

Every value comes from candles closed by the time it carries, and the trades are priced as Noculus prices a pseudo
trade (bid and ask, the spread floor, stop slippage, commission).
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from algo_research.fractal_poi.frames import PERIOD, period_end
from algo_research.replay.timeframes import aggregate, seconds_of

__all__ = ["BASE_BODY", "EXPIRY", "HOLD", "OUT_BODY", "OUT_RANGE", "STOP_BUFFER", "trade_zones", "zone_life", "zones"]

BASE_BODY, OUT_BODY, OUT_RANGE, MAX_BASE = 0.5, 0.6, 1.5, 3
STOP_BUFFER = 0.1
EXPIRY, HOLD = 30, 10


def zones(wall: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, tf: str) -> pd.DataFrame:
    """Every zone on ``tf`` candles aggregated from M1 (wall seconds), oldest first: kind, tf, known (the leg-out's
    close), base_from, base_n, proximal, distal, departure (the leg-out's range in average ranges)."""
    bars = aggregate(np.asarray(wall, dtype=np.int64), o, h, l, c, tf)
    t = bars["time"].to_numpy(np.int64)
    bo, bh, bl, bc = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    rng = bh - bl
    body = np.abs(bc - bo)
    avg = pd.Series(rng).rolling(20).mean().shift(1).to_numpy()            # the 20 candles before
    basing = (rng > 0) & (body <= BASE_BODY * rng)
    rows = []
    for j in range(1, len(t)):
        if not (rng[j] > 0 and body[j] >= OUT_BODY * rng[j] and np.isfinite(avg[j]) and rng[j] >= OUT_RANGE * avg[j]):
            continue
        k = j
        while k - 1 >= 0 and basing[k - 1] and j - (k - 1) <= MAX_BASE:
            k -= 1
        if k == j:
            continue                                                        # no base: a leg out of a leg
        base = slice(k, j)
        if bc[j] > bo[j] and bc[j] > bh[base].max():
            kind, proximal, distal = "DEMAND", np.maximum(bo[base], bc[base]).max(), min(bl[base].min(), bl[j])
        elif bc[j] < bo[j] and bc[j] < bl[base].min():
            kind, proximal, distal = "SUPPLY", np.minimum(bo[base], bc[base]).min(), max(bh[base].max(), bh[j])
        else:
            continue
        rows.append({"kind": kind, "tf": tf, "known": period_end(int(t[j]), PERIOD[tf]), "base_from": int(t[k]),
                     "base_n": j - k, "proximal": float(proximal), "distal": float(distal),
                     "departure": float(rng[j] / avg[j])})
    return pd.DataFrame(rows, columns=["kind", "tf", "known", "base_from", "base_n", "proximal", "distal", "departure"])


def zone_life(table: pd.DataFrame, wall: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> pd.DataFrame:
    """Each zone's ``first_touch`` (the first M1 after it is known to trade back to the proximal line) and ``broken``
    (the first M1 close beyond the distal line), in wall seconds; NaN when it never happens in the data."""
    wall = np.asarray(wall, dtype=np.int64)
    out = table.copy()
    touch, broke = [], []
    for z in table.itertuples():
        i0 = int(np.searchsorted(wall, z.known, side="left"))
        demand = z.kind == "DEMAND"
        hit = (l[i0:] <= z.proximal) if demand else (h[i0:] >= z.proximal)
        gone = (c[i0:] < z.distal) if demand else (c[i0:] > z.distal)
        touch.append(int(wall[i0 + int(np.argmax(hit))]) if hit.any() else np.nan)
        broke.append(int(wall[i0 + int(np.argmax(gone))]) if gone.any() else np.nan)
    out["first_touch"], out["broken"] = touch, broke
    return out


def trade_zones(table: pd.DataFrame, path: Mapping[str, np.ndarray], costs=None, target_r: float = 2.0) -> pd.DataFrame:
    """The first return to each zone as a limit at its proximal line (one row per zone)."""
    from algo_backtester.noculus import close, place, settle
    rows = []
    for z in table.itertuples():
        demand = z.kind == "DEMAND"
        height = abs(z.proximal - z.distal)
        stop = z.distal - STOP_BUFFER * height if demand else z.distal + STOP_BUFFER * height
        risk = abs(z.proximal - stop)
        target = z.proximal + target_r * risk if demand else z.proximal - target_r * risk
        sec = seconds_of(z.tf)
        expiry = int(z.known) + EXPIRY * sec
        body = {"direction": "LONG" if demand else "SHORT", "kind": "LIMIT", "price": float(z.proximal),
                "stop": float(stop), "target": float(target), "expiry": expiry}
        try:
            trade = place(body, path, int(z.known), until=expiry)
        except ValueError as exc:
            rows.append({"state": "REFUSED", "why": str(exc).split(":")[0]})
            continue
        settle(trade, path, expiry, costs)
        if trade["filled_at"] is not None:
            horizon = int(trade["filled_at"]) + HOLD * sec
            settle(trade, path, horizon, costs)
            if trade["state"] == "OPEN":
                close(trade, path, horizon, costs)
        rows.append({k: trade.get(k) for k in ("state", "outcome", "fill", "stop", "target", "risk", "gross_r", "net_r",
                                                "filled_at")})
    return pd.concat([table.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


# ── the run (python -m algo_research.supply_demand) ──────────────────────────────────────────────────────────
MARKETS = ("XAUUSD", "EURUSD", "GBPUSD", "US100", "US30")
TIMEFRAMES = ("D1", "H4", "H1")


def run(markets=MARKETS, paired_with: str | None = None) -> str:
    """Zones formed in the exploration slice, traded on their first return at 2R and 3R, per timeframe and market.
    ``paired_with``: a ``fractal_poi.diff --save`` pickle, to split its setups by whether C2 swept into a fresh zone
    of their kind (supply for shorts, demand for longs) on D1, H4 or H1."""
    from algo_research.config import load_research_config
    from algo_research.dataset import build_frames
    from algo_research.races import RaceCosts
    from algo_research.replay.timeframes import wall_seconds
    from algo_research.snapshot import SNAPSHOTS_DIR, load_snapshot
    from algo_research.specs import research_specs

    cfg = load_research_config()
    first, end = (pd.Timestamp(d, tz="UTC") for d in cfg.slices.explore)
    snapdir = SNAPSHOTS_DIR / cfg.snapshot
    specs = research_specs(cfg)
    frames = build_frames(load_snapshot(snapdir, list(markets)), specs)
    w_first, w_end = (int(wall_seconds([x])[0]) for x in (first, end))
    every_zone, every_trade = [], []
    for inst in markets:
        f = pd.read_parquet(snapdir / f"{inst}_M1.parquet", columns=["time", "open", "high", "low", "close"])
        f["time"] = pd.to_datetime(f["time"], utc=True)
        f = f[(f.time >= first - pd.Timedelta(days=60)) & (f.time < end + pd.Timedelta(days=12))]
        wall = wall_seconds(f.time)
        o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        frame = frames[inst]
        path = {"time": np.asarray(wall_seconds(frame.m1["time"]), dtype=np.int64),
                **{k: frame.arrays[k] for k in ("open", "high", "low", "close", "spread")}}
        costs = RaceCosts.from_spec(specs[inst], specs.account_ccy(inst))
        for tf in TIMEFRAMES:
            table = zone_life(zones(wall, o, h, l, c, tf), wall, h, l, c).assign(inst=inst)
            every_zone.append(table)
            table = table[(table.known >= w_first) & (table.known < w_end)]
            for r in (2.0, 3.0):
                every_trade.append(trade_zones(table, path, costs, r).assign(inst=inst, target_r=r))
    zs, ts = pd.concat(every_zone, ignore_index=True), pd.concat(every_trade, ignore_index=True)
    ts = ts[ts.state == "CLOSED"]
    lines = [f"# Supply and demand ({cfg.slices.explore[0]} to {cfg.slices.explore[1]}, exploration only)", "",
             "| Zones | Trades | Hit | Chance | Gross R | Net R | By market (net) |", "|---|---|---|---|---|---|---|"]
    for (tf, r), g in ts.groupby(["tf", "target_r"], sort=False):
        lines.append(f"| {tf}, {r:.0f}R | {len(g)} | {(g.outcome == 'TARGET').mean():.2f} | {1 / (1 + r):.2f} | "
                     f"{g.gross_r.mean():+.3f} | {g.net_r.mean():+.3f} | "
                     + ", ".join(f"{i} {x.net_r.mean():+.2f}" for i, x in g.groupby("inst")) + " |")
    if paired_with:
        lines += ["", *_paired(zs, pd.read_pickle(paired_with), w_first, w_end, snapdir, cfg)]
    return "\n".join(lines) + "\n"


def _paired(zs: pd.DataFrame, trades: pd.DataFrame, w_first: int, w_end: int, snapdir, cfg) -> list[str]:
    from algo_research.fractal_poi import FractalPOI, FractalSettings, partners_for, warmup_days
    from algo_research.fractal_poi.diff import windows
    from algo_research.fractal_poi.setups import setup_rows
    s = FractalSettings()
    held = [p.name.split("_")[0] for p in snapdir.glob("*_M1.parquet")]
    first = pd.Timestamp(cfg.slices.explore[0], tz="UTC") - pd.Timedelta(days=warmup_days("M15", s))
    end = pd.Timestamp(cfg.slices.explore[1], tz="UTC") + pd.Timedelta(days=2)

    def m1(inst):
        f = pd.read_parquet(snapdir / f"{inst}_M1.parquet", columns=["time", "open", "high", "low", "close"])
        f["time"] = pd.to_datetime(f["time"], utc=True)
        return f[(f.time >= first) & (f.time < end)]
    rows = []
    for inst in sorted(set(trades.instrument)):
        reader = FractalPOI(m1(inst), "M15", s, inst, {n: (m1(n), v) for n, v in partners_for(inst, s, held)},
                            archive=True)
        reader.at(w_end)
        st = setup_rows(reader)
        st = windows(st[(st.c2_open >= w_first) & (st.c2_open < w_end)])
        zi = zs[zs.inst == inst]
        for x in st.itertuples():
            kind = "SUPPLY" if x.direction == "SHORT" else "DEMAND"
            fresh = zi[(zi.kind == kind) & (zi.known < x.c2_open) & ~(zi.first_touch < x.c2_open) & ~(zi.broken < x.c2_open)]
            reached = (x.c2_extreme >= fresh.proximal) if kind == "SUPPLY" else (x.c2_extreme <= fresh.proximal)
            rows.append({"instrument": inst, "uid": x.uid, "zones": ",".join(sorted(set(fresh[reached].tf))) or "none"})
    paired = trades.merge(pd.DataFrame(rows), on=["instrument", "uid"], how="left")
    paired = paired[paired.state == "CLOSED"]
    lines = ["| The indicator's setups | n | Win | Gross R | Net R |", "|---|---|---|---|---|"]
    for v, name in (("A", "market at C2 + CISD"), ("B", "limit at the C3 zone's EQ edge")):
        g = paired[paired.variant == v]
        for label, mask in (("all", g.zones.notna()), ("C2 swept into a fresh zone", g.zones != "none"),
                            ("into no fresh zone", g.zones == "none")):
            x = g[mask]
            if len(x):
                lines.append(f"| {name}: {label} | {len(x)} | {(x.outcome == 'TARGET').mean():.2f} | "
                             f"{x.gross_r.mean():+.3f} | {x.net_r.mean():+.3f} |")
    return lines


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Supply and demand zones, traded on their first return.")
    parser.add_argument("--markets", nargs="+", default=list(MARKETS))
    parser.add_argument("--paired", help="a fractal_poi.diff --save pickle of the indicator's setups as trades")
    args = parser.parse_args(argv)
    print(run(args.markets, args.paired))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
