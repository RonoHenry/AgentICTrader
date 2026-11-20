"""H-AS: H-AR's frozen ladder system on sixteen markets it has never run on (registered 2026-11-19, before their data
is exported).

The trader (2026-11-19): "I think we can have other assets as well ... we can just go with all of them". The markets
are theirs: USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, AUDJPY, NZDJPY, EURCAD, GBPCAD, USOIL, JP225,
BTCUSD, ETHUSD and XRPUSD. The system is H-AR's, unchanged (``algo_research.search_ladder.signals`` and ``price``):
- the higher ladder (a live D1 CRT with W1 the same way), the signal (an H4, H1, M30 or M15 CRT at its C3), the order,
  the stop, the D1 target, the time exit and one slot per frame, market and arm;
- arms BASE_FULL (judged) and BASE_HALF (reported), each with its placebo. H-AR's D1-discount arm failed and isn't run.
What H-AS sets, because these markets are new:
- data: ``mt5-m1-assets`` (``scripts/export_mt5_history.py --timeframes M1 --start 2021-01-01 --symbols ...``), the
  Exness demo server's M1; a market the server doesn't carry is dropped (the manifest's ``unavailable``);
- signals from the later of 2021-10-03 and 80 days after the market's first intraday date (H-AR's warm-up), to the
  export's end;
- stop slippage: half the market's median M1 spread over its export (Exness gives no figure for these);
- the verdict: pooled over the markets, see ``verdict``.
Amended 2026-11-20, before the run: USOIL and JP225 are frozen (``FROZEN``). Exness has no prices for them on any
timeframe for two long stretches, so they're held back like the unavailable cryptos. The eleven FX markets run, and the
pass needs 7 of 11 positive.

    python -m algo_research.search_ladder_assets run --registered
    python -m algo_research.search_ladder_assets verdict
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from agent.brokers.fill_model import FillModel
from algo_research.search_ladder import NY, OUT, SEED, SNAPSHOTS, price, signals
from thesis_engine.replay import prepare
from thesis_engine.settings import V1

__all__ = ["ASSETS", "run_market", "verdict"]

#: The trader's markets and the class each is reported in.
ASSETS = {"USDJPY": "FX major", "AUDUSD": "FX major", "USDCAD": "FX major", "USDCHF": "FX major",
          "NZDUSD": "FX major", "EURJPY": "JPY cross", "GBPJPY": "JPY cross", "AUDJPY": "JPY cross",
          "NZDJPY": "JPY cross", "EURCAD": "CAD cross", "GBPCAD": "CAD cross", "USOIL": "energy", "JP225": "index",
          "BTCUSD": "crypto", "ETHUSD": "crypto", "XRPUSD": "crypto"}
SNAPSHOT = "mt5-m1-assets"
SIGNALS_FROM = pd.Timestamp("2021-10-03")
WARMUP_DAYS = 80
SLIPPAGE_SHARE = 0.5
ARMS = ("BASE_FULL", "BASE_HALF")
MARKET_SHARE = 0.6
#: Frozen before the run (2026-11-20, the trader's call): the server has no prices for these on any timeframe
#: (M1 to D1) for long stretches. They wait for another broker's complete history, under a new registration.
FROZEN = {"USOIL": "no prices 2023-06-30..2024-03-31 and 2026-07-17..2026-10-11 on any timeframe",
          "JP225": "no prices 2023-06-30..2024-03-31 and 2026-07-17..2026-10-11 on any timeframe"}


def since_for(manifest: dict, market: str) -> str:
    first = pd.Timestamp(manifest["markets"][market]["intraday_from"])
    return max(SIGNALS_FROM, first + pd.Timedelta(days=WARMUP_DAYS)).date().isoformat()


def run_market(market: str, manifest: dict, snapshot: str = SNAPSHOT) -> tuple[list, dict]:
    m1 = pd.read_parquet(SNAPSHOTS / snapshot / f"{market}_M1.parquet")
    m1 = m1.sort_values("time", kind="stable").reset_index(drop=True)
    since = since_for(manifest, market)
    sigs = signals(m1, market, int(pd.Timestamp(since).value // 10**9))
    mk = prepare(market, m1, V1)
    slip = SLIPPAGE_SHARE * float(np.median(m1["spread"].to_numpy(dtype=float)))
    fm = FillModel(slip)
    first = int(np.searchsorted(mk.t, pd.Timestamp(since, tz=NY).tz_convert("UTC").value, "left"))
    trades = []
    for arm in ARMS:
        half = arm.endswith("HALF")
        for tf, lst in sigs.items():
            rng = np.random.default_rng(zlib.crc32(f"H-AS|{SEED}|{market}|{arm}|{tf}".encode()))
            busy = busy_p = -1
            for n, sg in enumerate(lst):
                if sg["t0"] < busy:
                    continue
                rec, why = price(mk, fm, f"{market}-{arm}-{tf}-{n}", sg["t0"], sg["until"], sg["side"], sg["stop"],
                                 sg["own"], sg["d1"], half)
                if rec is None:
                    continue
                busy = rec["closed_at"]
                base = {"market": market, "class": ASSETS.get(market, "?"), "arm": arm, "tf": tf, "side": sg["side"]}
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
    return trades, {"since": since, "stop_slippage": slip, "signals": {tf: len(v) for tf, v in sigs.items()}}


def verdict(df: pd.DataFrame, markets: list, resamples: int = 10000) -> dict:
    """H-AS's pass rule on BASE_FULL, pooled over the markets run: R a trade above zero, above its placebo's, and at
    least 60% of the markets positive; confirmed when the 95% interval (resampling market-weeks) clears zero."""
    rng = np.random.default_rng(SEED)
    week = pd.to_datetime(df["t_place"], utc=True).dt.tz_convert(NY).dt.tz_localize(None).dt.to_period("W-SUN")
    df = df.assign(cluster=df["market"] + "|" + week.astype(str))
    out = {"markets_run": markets, "arms": {}}
    for arm in ARMS:
        r, p = df[(df.arm == arm) & (~df.placebo)], df[(df.arm == arm) & (df.placebo)]
        if not len(r):
            out["arms"][arm] = {"trades": 0}
            continue
        u, inv = np.unique(r["cluster"].to_numpy(), return_inverse=True)
        s = np.bincount(inv, weights=r["net_r"].to_numpy(), minlength=len(u))
        n = np.bincount(inv, minlength=len(u)).astype(float)
        idx = rng.integers(0, len(u), size=(resamples, len(u)))
        m = s[idx].sum(1) / n[idx].sum(1)
        by = r.groupby("market")["net_r"].sum()
        need = math.ceil(MARKET_SHARE * len(markets))
        pos = int(sum(by.get(mk, 0.0) > 0 for mk in markets))
        mean, plc = float(r["net_r"].mean()), float(p["net_r"].mean()) if len(p) else float("nan")
        lo, hi = np.percentile(m, [2.5, 97.5])
        out["arms"][arm] = {
            "trades": len(r), "R_a_trade": mean, "ci95": [float(lo), float(hi)], "placebo_R": plc,
            "markets_positive": pos, "markets_needed": need, "win": float((r["net_r"] > 0).mean()),
            "total_R": float(r["net_r"].sum()),
            "passes": bool(mean > 0 and mean > plc and pos >= need), "confirmed_95": bool(lo > 0),
            "by_class": {c: {"trades": int(len(g)), "R_a_trade": float(g["net_r"].mean())}
                         for c, g in r.groupby("class")},
            "by_market": {mk: {"trades": int(len(g)), "R_a_trade": float(g["net_r"].mean()),
                               "total_R": float(g["net_r"].sum())} for mk, g in r.groupby("market")}}
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m algo_research.search_ladder_assets")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--registered", action="store_true", help="H-AS is registered and committed")
    sub.add_parser("verdict")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SNAPSHOTS / SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    markets = [m for m in ASSETS if m in manifest["markets"] and m not in FROZEN]
    if args.cmd == "run":
        if not args.registered:
            raise SystemExit("H-AS runs once, after its registration is committed (--registered)")
        rows, info, t0 = [], {}, time.time()
        for m in markets:
            tr, meta = run_market(m, manifest)
            rows += tr
            info[m] = meta
            print(f"{m}: {sum(not x['placebo'] for x in tr)} real trades from {meta['since']} "
                  f"({time.time() - t0:.0f}s)", flush=True)
        pd.DataFrame(rows).to_parquet(OUT / "has_assets.parquet")
        (OUT / "has_assets_info.json").write_text(json.dumps({"markets": info, "unavailable":
                                                             manifest.get("unavailable", []), "frozen": FROZEN},
                                                            indent=1), encoding="utf-8")
    else:
        df = pd.read_parquet(OUT / "has_assets.parquet")
        res = verdict(df, markets)
        (OUT / "has_assets_verdict.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
