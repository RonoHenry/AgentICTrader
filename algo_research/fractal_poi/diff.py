"""The indicator's setups against the engine's decisions, and the setups as trades (algo-backtester Requirement 24).

    python -m algo_research.fractal_poi.diff [--run <backtest dir>] [--instruments XAUUSD EURUSD GBPUSD] [--out f.md]

It reads a backtest run's journal (the engine's decision at every M15 close, with each order's raid and entry array)
and the indicator's setups on an M15 chart (HTF H4) over the research configuration's **exploration slice** only.
For each instrument it reports:
- **the engine's orders,** each with, against, or outside a live indicator setup; whether its raid was C1's extreme;
  the raid's age; the entry array;
- **each setup,** what the engine did during it (traded with, traded against, out by its limits, in another trade,
  graded out, R:R below its floor, another raid, no sequence);
- **the setups as trades,** priced as Noculus prices a pseudo trade (bid and ask, the spread floor, stop slippage,
  commission):
  - A: market once C2 has closed back inside C1 and the CISD has broken;
  - B: a limit at the C3 zone's EQ edge, until C3 closes;
  - C: a limit at the C4 zone's edge with the stop at C3's extreme, until C4 closes.

  Each is read alone, with the trading day's real direction (hindsight, an upper bound), and with the previous day's.

**No look-ahead.** An order uses only what was known when it is placed. In particular, C3's and C4's closes come
from the HTF clock (``period_end``), never from the setup's later record. Only a setup that survives C3 gets a C4,
so reading the expiry from that record silently drops every setup that went on to fail (2026-10-20: it turned
B's −0.14R into +0.58R).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from algo_research.fractal_poi.frames import period_end
from algo_research.fractal_poi.setups import known_at
from algo_research.replay.timeframes import aggregate, wall_seconds

__all__ = ["VARIANTS", "classify_orders", "engine_during", "trade_setups", "windows"]

VARIANTS = {"A": "market at C2 + CISD", "B": "limit at the C3 zone's EQ edge", "C": "limit at the C4 zone, stop at C3"}
_RAID = re.compile(r"Raid of (\w+) \((\w+)\) at ([\d.]+)")
_HIGHS = {"SWING_HIGH", "PDH", "PWH", "PMH", "ASIA_HIGH", "EQUAL_HIGHS"}
#: A raid is C1's extreme when within 5% of C1's range of it.
RAID_TOLERANCE = 0.05


def windows(setups: pd.DataFrame) -> pd.DataFrame:
    """Each setup's live window: from when it can first be traded (``known``) to C4's close, or the xC2 before it."""
    out = setups.copy()
    out["known"] = [known_at(r) for _, r in out.iterrows()]
    out = out[out["known"].notna()].copy()
    c3_close = [period_end(int(c3), htf) for c3, htf in zip(out.c3_open, out.htf)]
    out["c3_close"] = c3_close
    out["c4_end"] = [period_end(c, htf) for c, htf in zip(c3_close, out.htf)]
    out["w0"] = out["known"].astype(np.int64)
    out["w1"] = [int(min(e, inv)) if pd.notna(inv) else int(e) for e, inv in zip(out.c4_end, out.invalid_at)]
    return out[out.w1 > out.w0].reset_index(drop=True)


def _c1_range(s) -> float:
    return abs(float(s.sweep_price) - float(s.target_c1))


def classify_orders(orders: pd.DataFrame, setups: pd.DataFrame) -> pd.DataFrame:
    """Each engine order (``tw``, its close in wall seconds; ``direction``; ``raid``, the swept pool) against the
    setups live at it: ``cls`` with / against / outside, and ``raid_is_c1``."""
    cls, raid_is_c1 = [], []
    for o in orders.itertuples():
        live = setups[(setups.w0 <= o.tw) & (setups.w1 > o.tw)]
        same = live[live.direction == o.direction]
        cls.append("with" if len(same) else "against" if len(live) else "outside")
        raid = getattr(o, "raid", None)
        if len(same) and raid and _c1_range(same.iloc[-1]):
            raid_is_c1.append(abs(raid["price"] - same.iloc[-1].sweep_price) / _c1_range(same.iloc[-1]) <= RAID_TOLERANCE)
        else:
            raid_is_c1.append(None)
    return orders.assign(cls=cls, raid_is_c1=raid_is_c1)


def engine_during(setups: pd.DataFrame, journal: pd.DataFrame) -> list[str]:
    """What the engine did at the M15 closes of each setup's window, most decisive first."""
    out = []
    for s in setups.itertuples():
        jj = journal[(journal.tw >= s.w0) & (journal.tw < s.w1)]
        ex = jj[jj.decision == "EXECUTE"]
        if (ex.direction == s.direction).any():
            out.append("traded with")
            continue
        if len(ex):
            out.append("traded against")
            continue
        decisions = Counter(jj.decision)
        if decisions.get("IN_TRADE", 0) >= max(1, len(jj) / 2):
            out.append("in another trade")
            continue
        if decisions.get("SKIP"):
            out.append("out by its limits")
            continue
        raids = [m for m in (_RAID.search(str(x)) for x in jj[jj.decision.isin(["NO_TRADE", "RR_BELOW_MIN"])].reason) if m]
        side = [m for m in raids if (m.group(1) in _HIGHS) == (s.direction == "SHORT")]
        width = _c1_range(s) or np.nan
        c1 = [m for m in side if abs(float(m.group(3)) - s.sweep_price) / width <= RAID_TOLERANCE]
        if decisions.get("RR_BELOW_MIN") and side:
            out.append("its setup, R:R below the floor")
        elif c1:
            out.append("raided C1, graded out")
        elif side:
            out.append("another raid, graded out")
        elif raids:
            out.append("only the other side's raids")
        else:
            out.append("no sequence")
    return out


def _trade(path, costs, direction, kind, at, stop, target, horizon, price=None, expiry=None) -> dict:
    from algo_backtester.noculus import close, place, settle
    body = {"direction": direction, "kind": kind, "stop": float(stop), "target": float(target)}
    if kind == "LIMIT":
        body.update(price=float(price), expiry=int(expiry))
    try:
        trade = place(body, path, int(at), until=int(horizon))
    except ValueError as exc:
        return {"state": "REFUSED", "why": str(exc).split(":")[0]}
    settle(trade, path, int(horizon), costs)
    if trade["state"] == "OPEN":
        close(trade, path, int(horizon), costs)
    return trade


def trade_setups(setups: pd.DataFrame, path: Mapping[str, np.ndarray], costs=None) -> pd.DataFrame:
    """The variants of ``VARIANTS`` for each setup of ``windows(setups)``, one row per order."""
    rows = []
    for s in setups.itertuples():
        short = s.direction == "SHORT"
        orders = [("A", "MARKET", s.known, s.c2_extreme, s.target_c1, s.c4_end, None, None)]
        if pd.notna(s.z3_low) and s.known < s.c3_close:
            orders.append(("B", "LIMIT", s.known, s.c2_extreme, s.target_c1, s.c4_end, s.z3_high if short else s.z3_low,
                           s.c3_close))
        if pd.notna(s.z4_low) and pd.isna(s.invalid_at):          # C4's zone is set at C4's open, after C3's xC2
            orders.append(("C", "LIMIT", s.c3_close, s.c3_extreme, s.target_c1, s.c4_end + (s.c4_end - s.c3_close),
                           s.z4_high if short else s.z4_low, s.c4_end))
        for variant, kind, at, stop, target, horizon, price, expiry in orders:
            x = _trade(path, costs, s.direction, kind, at, stop, target, horizon, price, expiry)
            rows.append({"variant": variant, "uid": s.uid, "direction": s.direction, "known": s.known,
                         "state": x.get("state"), "outcome": x.get("outcome"), "why": x.get("why"),
                         "fill": x.get("fill"), "stop": x.get("stop"), "target": x.get("target"), "risk": x.get("risk"),
                         "gross_r": x.get("gross_r"), "net_r": x.get("net_r")})
    return pd.DataFrame(rows)


def _day_directions(m1: pd.DataFrame) -> pd.DataFrame:
    """Each trading day's direction (+1 up, -1 down) and the previous day's, by the day's 17:00 open in wall seconds."""
    wall = wall_seconds(pd.to_datetime(m1["time"], utc=True))
    d1 = aggregate(wall, *(m1[k].to_numpy(float) for k in ("open", "high", "low", "close")), "D1")
    d1["dir"] = np.sign(d1.close - d1.open)
    d1["prev"] = d1["dir"].shift(1)
    return d1.set_index("time")[["dir", "prev"]]


def _table(trades: pd.DataFrame) -> list[str]:
    sign = np.where(trades.direction == "LONG", 1, -1)
    lines = ["| Setups as trades | Filled | Win | Break-even win | Gross R | Net R | Total |",
             "|---|---|---|---|---|---|---|"]
    for v, name in VARIANTS.items():
        for label, mask in (("", trades.variant == v),
                            (" — with the day's real direction (hindsight)", (trades.variant == v) & (sign == trades.dir)),
                            (" — against it", (trades.variant == v) & (sign == -trades.dir)),
                            (" — with the previous day's", (trades.variant == v) & (sign == trades.prev))):
            x = _summary(trades[mask])
            if x["n"]:
                lines.append(f"| {v}: {name}{label} | {x['n']} | {x['win']:.2f} | {x['break_even']:.2f} | "
                             f"{x['gross']:+.3f} | {x['net']:+.3f} | {x['total']:+.1f} |")
    return lines


def _summary(trades: pd.DataFrame) -> dict:
    f = trades[trades.state == "CLOSED"]
    if f.empty:
        return {"n": 0}
    reward = (f.fill - f.target).abs()
    return {"n": len(f), "win": float((f.outcome == "TARGET").mean()), "break_even": float((f.risk / (f.risk + reward)).mean()),
            "gross": float(f.gross_r.mean()), "net": float(f.net_r.mean()), "total": float(f.net_r.sum())}


# ── the run ──────────────────────────────────────────────────────────────────────────────────────────────────
def run(instruments, run_dir: Path, out: Optional[Path] = None) -> str:
    from algo_research.config import load_research_config
    from algo_research.dataset import build_frames
    from algo_research.fractal_poi import FractalPOI, FractalSettings, partners_for, warmup_days
    from algo_research.fractal_poi.setups import setup_rows
    from algo_research.races import RaceCosts
    from algo_research.snapshot import SNAPSHOTS_DIR, load_snapshot
    from algo_research.specs import research_specs

    cfg = load_research_config()
    first, end = cfg.slices.explore
    start_utc, end_utc = pd.Timestamp(first, tz="UTC"), pd.Timestamp(end, tz="UTC")
    snapdir = SNAPSHOTS_DIR / cfg.snapshot
    held = [p.name.split("_")[0] for p in snapdir.glob("*_M1.parquet")]
    s = FractalSettings()
    days = warmup_days("M15", s)

    def m1(inst: str) -> pd.DataFrame:
        f = pd.read_parquet(snapdir / f"{inst}_M1.parquet", columns=["time", "open", "high", "low", "close"])
        f["time"] = pd.to_datetime(f["time"], utc=True)
        return f[(f.time >= start_utc - pd.Timedelta(days=days)) & (f.time < end_utc + pd.Timedelta(days=2))]

    def wall(values) -> np.ndarray:
        return wall_seconds(pd.to_datetime(values, utc=True))

    journal = pd.read_csv(run_dir / "journal.csv", low_memory=False)
    journal["t_utc"] = pd.to_datetime(journal["t"], utc=True)
    context = {c["setup_id"]: c["context"] for c in json.loads((run_dir / "context.json").read_text(encoding="utf-8"))}
    specs = research_specs(cfg)
    frames = build_frames(load_snapshot(snapdir, instruments), specs)
    lines = [f"# The indicator's setups against the engine ({first} to {end}, exploration only)", "",
             f"Engine: `{run_dir.name[:12]}` (its journal). Indicator: M15 chart, HTF H4, default inputs.", ""]
    every_trade, every_order, every_setup = [], [], []
    for inst in instruments:
        reader = FractalPOI(m1(inst), "M15", s, inst, {n: (m1(n), inv) for n, inv in partners_for(inst, s, held)},
                            archive=True)
        end_wall = int(wall([end_utc])[0])
        reader.at(end_wall)
        setups = setup_rows(reader)
        setups = windows(setups[(setups.c2_open >= int(wall([start_utc])[0])) & (setups.c2_open < end_wall)])
        j = journal[(journal.instrument == inst) & (journal.t_utc >= start_utc) & (journal.t_utc < end_utc)].copy()
        j["tw"] = wall(j["t_utc"])
        orders = j[j.decision == "EXECUTE"].copy()
        orders["raid"] = [context.get(x, {}).get("swept_level") for x in orders.setup_id]
        orders["array"] = [context.get(x, {}).get("entry_array") for x in orders.setup_id]
        orders = classify_orders(orders, setups)
        setups["engine"] = engine_during(setups, j)
        frame = frames[inst]
        path = {"time": np.asarray(wall_seconds(frame.m1["time"]), dtype=np.int64),
                **{k: frame.arrays[k] for k in ("open", "high", "low", "close", "spread")}}
        trades = trade_setups(setups, path, RaceCosts.from_spec(specs[inst], specs.account_ccy(inst)))
        days_ = _day_directions(m1(inst))
        day = ((trades.known.astype(np.int64) - 61200) // 86400) * 86400 + 61200
        trades = trades.join(days_, on=day.rename("day"))
        every_trade.append(trades)
        every_order.append(orders)
        every_setup.append(setups)
        filled = orders[orders.filled_at.notna()]
        ages = [(o.tw - int(wall([o.raid["raided_at"]])[0])) / 3600 for o in orders.itertuples() if o.raid]
        lines += [f"## {inst}", "",
                  f"- **The indicator:** {len(setups)} setups (C2 closed back inside C1 and its CISD broke), "
                  f"{int(setups.invalid_at.notna().sum())} of them an xC2 in C3.",
                  f"- **The engine:** {len(orders)} orders, {len(filled)} filled, {filled.net_r.sum():+.1f}R net. "
                  f"With a live setup: {int((orders.cls == 'with').sum())}; against one: {int((orders.cls == 'against').sum())}; "
                  f"outside any: {int((orders.cls == 'outside').sum())}.",
                  f"- **Its raid was C1's extreme** in {int((orders.raid_is_c1 == True).sum())} of its "  # noqa: E712
                  f"{int((orders.cls == 'with').sum())} orders with a setup. The raid's median age at the order was "
                  f"{np.median(ages):.1f} h ({np.mean(np.array(ages) > 4):.0%} over 4 h).",
                  "- **Its entry arrays:** " + ", ".join(f"{k} {v}" for k, v in Counter(
                      f"{a['timeframe']} {a['type']}" for a in orders.array if a).most_common(4)) + ".",
                  "- **During the indicator's setups the engine:** " + ", ".join(
                      f"{k} {v}" for k, v in setups.engine.value_counts().items()) + ".", ""]
        lines += _table(trades) + [""]
    if len(instruments) > 1:
        trades, orders, setups = (pd.concat(x, ignore_index=True) for x in (every_trade, every_order, every_setup))
        filled = orders[orders.filled_at.notna()]
        lines += [f"## All {len(instruments)}", "",
                  f"- {len(setups)} indicator setups; the engine's {len(orders)} orders ({len(filled)} filled, "
                  f"{filled.net_r.sum():+.1f}R): {int((orders.cls == 'with').sum())} with a setup, "
                  f"{int((orders.cls == 'against').sum())} against one, {int((orders.cls == 'outside').sum())} outside any.",
                  "- Engine net R per filled trade: " + ", ".join(
                      f"{k} {g.net_r.mean():+.2f} ({len(g)})" for k, g in filled.groupby("cls")) + ".", ""]
        lines += _table(trades) + [""]
    text = "\n".join(lines) + "\n"
    if out is not None:
        Path(out).write_text(text, encoding="utf-8")
    return text


def main(argv=None) -> int:
    from algo_backtester.config import REPO_ROOT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, help="a backtest run's directory (default: the latest base run)")
    parser.add_argument("--instruments", nargs="+", default=["XAUUSD", "EURUSD", "GBPUSD"])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    run_dir = args.run
    if run_dir is None:
        runs = sorted((p for p in (REPO_ROOT / "data" / "backtests").iterdir() if (p / "summary.md").exists()
                       and "variant: base" in (p / "summary.md").read_text(encoding="utf-8")[:2000]),
                      key=lambda p: p.stat().st_mtime)
        if not runs:
            print("no base backtest run under data/backtests", file=sys.stderr)
            return 1
        run_dir = runs[-1]
    print(run(args.instruments, run_dir, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
