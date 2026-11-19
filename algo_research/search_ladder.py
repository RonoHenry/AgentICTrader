"""H-AR: the ladder pullback system (registered 2026-11-19, before its one run on July to November 2026).

The trader's idea (2026-11-18): "if the higher ladder agrees, we find pullbacks that align with them on the lower
time frame ... and aim for those higher time frame targets while taking partials in the process". Developed on the
read windows in ``data/research/one_system`` (ladder_pullbacks.py, ladder_system.py, ladder_refined.py, ladder_pd.py);
registered in docs/research/SEARCH_2018_2024.md. Everything below comes from the trader's Fractal + POI indicator
(``algo_research.fractal_poi``, Automatic mode), read on closed candles only.

**The higher ladder:** a live D1 CRT (the indicator on the H1 chart) with the W1 CRT (H4 chart) live the same way.
Live: C3 known (C3's open and the CISD), not invalidated, before C4 closes.

**The signal:** an H4 (M15 chart), H1 (M5 chart), M30 (M3 chart) or M15 (M1 chart) CRT pointing the same way, at the
moment its C3 is known; the ladder must agree at that moment.

**The order:** at market, filled by the shared fill model (``agent.brokers.fill_model``) on M1 bars from the next
bar's open (the ask for a buy, the bid for a sell), with Exness's stop slippage (config/instruments). The stop at the
signal's C2 extreme, at least 10 typical spreads from the expected entry (the last close, plus the spread for a buy);
the D1 CRT's target (C1's opposite extreme) must be beyond the expected entry. Out at the D1 CRT's C4 close (the last
bar's close), or at the data's end.

**The arms** (each entry frame keeps its own one-position slot per market and arm):
- BASE_FULL: one order to the D1 target;
- BASE_HALF: two half orders, one to the signal's own C1 target and one to the D1 target (no break-even move; HALF
  is FULL when the own target isn't nearer);
- D1DISC_FULL and D1DISC_HALF: the same, taking only signals whose expected entry is in discount (a buy) or premium
  (a sell) of the D1 swing dealing range at that moment (``thesis_engine`` book's ``frames['D1'].range``, < 0.5 or
  > 0.5 of it).
Each arm has a placebo: for each trade, the same side, distances and horizon from a random M1 bar of the window, its
own slot. Net R as the engine's ``_r``: the prices paid over the planned risk.

    python -m algo_research.search_ladder run --windows develop,test,year
    python -m algo_research.search_ladder run --windows holdout --registered     # once, after registration
    python -m algo_research.search_ladder verdict --window holdout
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import numpy as np
import pandas as pd

from agent.brokers.fill_model import Bar, FillModel, SimOrder
from algo_research.fractal_poi import _arrays
from algo_research.fractal_poi.chart import Chart
from algo_research.fractal_poi.model import Model
from algo_research.fractal_poi.settings import FractalSettings
from algo_research.fractal_poi.setups import setup_rows
from thesis_engine.replay import _close_at, _r, prepare
from thesis_engine.settings import V1

__all__ = ["ARMS", "MARKETS", "WINDOWS", "run_market", "signals", "verdict"]

REPO = Path(__file__).resolve().parents[1]
SNAPSHOTS = REPO / "data" / "research" / "snapshots"
OUT = REPO / "data" / "research" / "ladder"
NY = "America/New_York"
MARKETS = ("XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
#: snapshot, the first M1 read (None: all), the first signal's New York date.
WINDOWS = {"develop": ("mt5-m1-develop", None, "2021-10-03"),
           "test": ("mt5-m1-test", None, "2023-01-01"),
           "year": ("focus-2025-2026h1", "2025-01-01", "2025-07-06"),
           "holdout": ("mt5-m1-2026-11", None, "2026-07-07")}
SETUP_CHART = {"H4": "M15", "H1": "M5", "M30": "M3", "M15": "M1"}
LADDER_CHART = {"D1": "H1", "W1": "H4"}
MIN_SPREADS = 10.0
ARMS = ("BASE_FULL", "BASE_HALF", "D1DISC_FULL", "D1DISC_HALF")
SEED = 20261119
SPECS = tomllib.loads((REPO / "config" / "instruments" / "exness-standard.toml").read_text(encoding="utf-8"))


# ── the indicator's setups ────────────────────────────────────────────────────
def read_chart(m1: pd.DataFrame, tf_chart: str, symbol: str):
    chart = Chart(*_arrays(m1), tf_chart)
    model = Model(chart, FractalSettings(), symbol, (), None, archive=True)
    for i in range(chart.n):
        model.step(i)
    return chart, model


def _table(rows: pd.DataFrame) -> dict:
    f = lambda c, fill: rows[c].astype("Float64").fillna(fill).to_numpy(dtype=float)   # noqa: E731
    return {"dir": np.where(rows["direction"].to_numpy() == "LONG", 1, -1),
            "known": np.maximum(f("c3_open", np.inf), f("cisd_at", np.inf)),
            "c4o": f("c4_open", np.inf), "c4c": f("c4_close", np.inf),
            "inv": f("invalid_at", np.inf), "inv4": f("c4_invalid_at", np.inf),
            "target": f("target_c1", np.nan)}


def _live(tab: dict, w: float, side: int):
    """(state, index of the newest live setup the same way) at wall time w."""
    on = (tab["known"] <= w) & (w < tab["c4c"]) & (tab["inv"] > w) & ((w < tab["c4o"]) | (tab["inv4"] > w))
    same, other = on & (tab["dir"] == side), on & (tab["dir"] != side)
    k = None
    if same.any():
        idx = np.flatnonzero(same)
        k = int(idx[np.argmax(tab["known"][idx])])
    state = "MIXED" if same.any() and other.any() else "ALIGNED" if same.any() else "CONFLICT" if other.any() \
        else "NONE"
    return state, k


def to_utc(wall: int) -> int:
    ts = pd.Timestamp(int(wall), unit="s").tz_localize(NY, ambiguous=False, nonexistent="shift_forward")
    return int(ts.tz_convert("UTC").value)


def signals(m1: pd.DataFrame, market: str, since_wall: int) -> dict:
    """{entry frame: [signal, ...]}, oldest first: each frame's CRTs at their C3 with the ladder agreeing."""
    tabs = {}
    for tf, ch in LADDER_CHART.items():
        c, mdl = read_chart(m1, ch, market)
        tabs[tf] = _table(setup_rows(SimpleNamespace(model=mdl, chart=c)))

    def ladder_at(w: int, side: int):
        _, kd = _live(tabs["D1"], w, side)
        if kd is None or _live(tabs["W1"], w, side)[0] != "ALIGNED":
            return None
        d1, until = float(tabs["D1"]["target"][kd]), float(tabs["D1"]["c4c"][kd])
        return (d1, until) if np.isfinite(d1) and np.isfinite(until) else None

    out = {}
    for tf, ch_tf in SETUP_CHART.items():
        chart, model = read_chart(m1, ch_tf, market)
        lst = []
        for s in model.archive:
            if s.ez_c3_left_time is None or s.cisd_end_idx is None or s.c2_extreme is None or s.liq_c1_price is None:
                continue
            if np.isnan(float(s.c2_extreme)) or np.isnan(float(s.liq_c1_price)):
                continue
            known = int(max(s.ez_c3_left_time, chart.end[s.cisd_end_idx]))
            if known < since_wall:
                continue
            side = 1 if s.is_bullish else -1
            lad = ladder_at(known, side)
            if lad is not None:
                lst.append({"tf": tf, "t0": to_utc(known), "side": side, "stop": float(s.c2_extreme),
                            "own": float(s.liq_c1_price), "d1": lad[0], "until": to_utc(int(lad[1]))})
        out[tf] = sorted(lst, key=lambda x: x["t0"])
    return out


# ── pricing ───────────────────────────────────────────────────────────────────
def _dt(ns: int) -> datetime:
    return datetime.fromtimestamp(int(ns) / 1e9, tz=timezone.utc)


def expected_entry(mk, t_place: int, side: int) -> tuple[int, Optional[float]]:
    i = int(np.searchsorted(mk.t, t_place, "left"))
    if i <= 0 or i >= len(mk.t):
        return i, None
    return i, float(mk.c[i - 1]) + (float(mk.spread[i - 1]) if side == 1 else 0.0)


def d1_discount(mk, t_place: int, entry: float, side: int) -> Optional[bool]:
    fr = mk.book.frames["D1"]
    r = fr.range(fr.n(int(t_place)))
    if r is None:
        return None
    p = r.position(float(entry))
    return (p < 0.5) if side == 1 else (p > 0.5)


def price(mk, fm: FillModel, oid: str, t_place: int, until: int, side: int, stop: float, own: float, d1: float,
          half: bool):
    """One trade through the fill model: (record, "OK") or (None, why)."""
    i, entry = expected_entry(mk, t_place, side)
    if entry is None or mk.t[i] >= until:
        return None, "NO_BARS"
    long_ = side == 1
    risk = (entry - stop) * side
    if risk < MIN_SPREADS * mk.typical_spread:
        return None, "FLOOR"
    if (d1 - entry) * side <= 0:
        return None, "BEHIND"
    nearer = 0 < (own - entry) * side < (d1 - entry) * side
    legs = [(0.5, own), (0.5, d1)] if half and nearer else [(1.0, d1)]
    orders = [SimOrder(f"{oid}-{k}", oid, mk.name, "LONG" if long_ else "SHORT", "MARKET", entry, stop, tgt,
                       placed_at=_dt(t_place)) for k, (_, tgt) in enumerate(legs)]
    spread_fill = float(mk.spread[i])
    live, prev, j = set(range(len(orders))), None, i
    while live and j < len(mk.t):
        b = Bar(_dt(mk.t[j]), float(mk.o[j]), float(mk.h[j]), float(mk.l[j]), float(mk.c[j]), float(mk.spread[j]))
        if mk.t[j] >= until and prev is not None:
            for k in list(live):
                if orders[k].status == "OPEN":
                    _close_at(orders[k], prev, "TIME")
                live.discard(k)
            break
        for k in list(live):
            for ev in fm.step(orders[k], b):
                if ev.kind in ("SL", "TP", "REJECTED", "EXPIRED"):
                    live.discard(k)
        prev, j = b, j + 1
    for k in list(live):                                           # the data ended with a position open
        if orders[k].status == "OPEN" and prev is not None:
            _close_at(orders[k], prev, "END")
    if any(o.fill is None for o in orders):
        return None, "REJECTED"
    if any(o.exit is None for o in orders):
        return None, "UNFILLED_AT_END"
    net = sum(w * _r(o, spread_fill, stop)[0] for (w, _), o in zip(legs, orders))
    gross = sum(w * _r(o, spread_fill, stop)[1] for (w, _), o in zip(legs, orders))
    closed = max(int(o.closed_at.timestamp() * 1e9) for o in orders)
    return {"net_r": net, "gross_r": gross, "fill": orders[0].fill, "risk": risk,
            "risk_spreads": risk / mk.typical_spread, "rr_d1": (d1 - entry) * side / risk,
            "exits": "+".join(o.exit_reason or "?" for o in orders), "closed_at": closed}, "OK"


def run_market(window: str, market: str) -> tuple[list, dict]:
    snap, bars_from, since = WINDOWS[window]
    m1 = pd.read_parquet(SNAPSHOTS / snap / f"{market}_M1.parquet")
    if bars_from is not None:
        m1 = m1[m1["time"] >= pd.Timestamp(bars_from, tz="UTC")].reset_index(drop=True)
    m1 = m1.sort_values("time", kind="stable").reset_index(drop=True)
    sigs = signals(m1, market, int(pd.Timestamp(since).value // 10**9))
    mk = prepare(market, m1, V1)
    fm = FillModel(float(SPECS[market]["stop_slippage"]))
    first = int(np.searchsorted(mk.t, pd.Timestamp(since, tz=NY).tz_convert("UTC").value, "left"))
    trades, counts = [], {}
    for arm in ARMS:
        half, disc = arm.endswith("HALF"), arm.startswith("D1DISC")
        for tf, lst in sigs.items():
            rng = np.random.default_rng(zlib.crc32(f"H-AR|{SEED}|{window}|{market}|{arm}|{tf}".encode()))
            busy = busy_p = -1
            for n, sg in enumerate(lst):
                if sg["t0"] < busy:
                    continue
                if disc:
                    _, entry = expected_entry(mk, sg["t0"], sg["side"])
                    if entry is None or not d1_discount(mk, sg["t0"], entry, sg["side"]):
                        counts[(arm, tf, "NOT_DISCOUNT")] = counts.get((arm, tf, "NOT_DISCOUNT"), 0) + 1
                        continue
                rec, why = price(mk, fm, f"{market}-{arm}-{tf}-{n}", sg["t0"], sg["until"], sg["side"], sg["stop"],
                                 sg["own"], sg["d1"], half)
                counts[(arm, tf, why)] = counts.get((arm, tf, why), 0) + 1
                if rec is None:
                    continue
                busy = rec["closed_at"]
                base = {"window": window, "market": market, "arm": arm, "tf": tf, "side": sg["side"]}
                trades.append({**base, "placebo": False, "t_place": sg["t0"], **rec})
                k = first
                for _try in range(20):
                    k = int(rng.integers(first, max(first + 1, len(mk.t) - 2)))
                    if int(mk.t[k]) >= busy_p:
                        break
                tp = int(mk.t[k])
                off = (float(mk.c[k - 1]) + (float(mk.spread[k - 1]) if sg["side"] == 1 else 0.0)) - rec["fill"]
                prec, _ = price(mk, fm, f"{market}-{arm}-{tf}-P{n}", tp, tp + (sg["until"] - sg["t0"]), sg["side"],
                                sg["stop"] + off, sg["own"] + off, sg["d1"] + off, half)
                if prec is not None:
                    busy_p = prec["closed_at"]
                    trades.append({**base, "placebo": True, "t_place": tp, **prec})
    return trades, counts


# ── the verdict (H-AR's pass rule) ────────────────────────────────────────────
def verdict(df: pd.DataFrame, resamples: int = 10000) -> pd.DataFrame:
    """Per arm, pooled over its four frames: R a trade with 95% and 97.5% intervals (resampling market-weeks),
    the placebo's R a trade, markets positive, and the three conditions of the pass rule."""
    rng = np.random.default_rng(SEED)
    week = pd.to_datetime(df["t_place"], utc=True).dt.tz_convert(NY).dt.tz_localize(None).dt.to_period("W-SUN")
    df = df.assign(cluster=df["market"] + "|" + week.astype(str))
    rows = []
    for arm in ARMS:
        r, p = df[(df.arm == arm) & (~df.placebo)], df[(df.arm == arm) & (df.placebo)]
        if not len(r):
            rows.append({"arm": arm, "trades": 0})
            continue
        u, inv = np.unique(r["cluster"].to_numpy(), return_inverse=True)
        s = np.bincount(inv, weights=r["net_r"].to_numpy(), minlength=len(u))
        n = np.bincount(inv, minlength=len(u)).astype(float)
        idx = rng.integers(0, len(u), size=(resamples, len(u)))
        m = s[idx].sum(1) / n[idx].sum(1)
        by = r.groupby("market")["net_r"].sum()
        pos = int(sum(by.get(mk, 0.0) > 0 for mk in MARKETS))
        mean, plc = float(r["net_r"].mean()), float(p["net_r"].mean()) if len(p) else float("nan")
        rows.append({"arm": arm, "trades": len(r), "R_a_trade": mean, "ci95": list(np.percentile(m, [2.5, 97.5])),
                     "ci975": list(np.percentile(m, [1.25, 98.75])), "placebo_R": plc, "markets_positive": pos,
                     "win": float((r["net_r"] > 0).mean()), "total_R": float(r["net_r"].sum()),
                     "cond_positive": mean > 0, "cond_beats_placebo": bool(mean > plc),
                     "cond_markets": pos >= 5, "passes": bool(mean > 0 and mean > plc and pos >= 5),
                     "confirmed_95": bool(np.percentile(m, 2.5) > 0),
                     "confirmed_holm": bool(np.percentile(m, 1.25) > 0)})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m algo_research.search_ladder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--windows", default="develop,test,year")
    r.add_argument("--registered", action="store_true", help="allow the hold-out (H-AR is registered)")
    v = sub.add_parser("verdict")
    v.add_argument("--window", default="holdout")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.cmd == "run":
        windows = [w for w in args.windows.split(",") if w]
        if "holdout" in windows and not args.registered:
            raise SystemExit("the hold-out runs once, after H-AR's registration is committed (--registered)")
        t0 = time.time()
        for w in windows:
            rows, counts = [], {}
            for m in MARKETS:
                tr, c = run_market(w, m)
                rows += tr
                counts.update({f"{m}|{a}|{tf}|{why}": v for (a, tf, why), v in c.items()})
                print(f"{w} {m}: {sum(not x['placebo'] for x in tr)} real trades ({time.time() - t0:.0f}s)", flush=True)
            pd.DataFrame(rows).to_parquet(OUT / f"har_{w}.parquet")
            (OUT / f"har_{w}_counts.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    else:
        df = pd.read_parquet(OUT / f"har_{args.window}.parquet")
        res = verdict(df)
        (OUT / f"har_{args.window}_verdict.json").write_text(res.to_json(orient="records", indent=1), encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        pd.set_option("display.width", 220)
        print(res.to_string(index=False))


if __name__ == "__main__":
    main()
