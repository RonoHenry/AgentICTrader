"""H-AT: H-AR's frozen ladder system on BTCUSD, ETHUSD and XRPUSD, from Binance spot M1 (registered 2026-11-20,
after the data was exported and checked for gaps and before any signal is computed on it).

The trader (2026-11-20): bring back the markets H-AS dropped, with data from sources that need no broker account.
Exness's Kenyan server offers no crypto, so the bars are Binance spot's (``scripts/export_free_history.py binance``,
snapshot ``binance-m1-crypto``). The system is H-AR's, unchanged (``algo_research.search_ladder.signals`` and
``price``): arms BASE_FULL (judged) and BASE_HALF (reported), each with its placebo, run as H-AS's runner runs them.
What H-AT sets, because a crypto venue charges a fee, not a spread:
- the bars carry no spread, so the cost is a fee of 0.1% of the notional a side (Binance spot's taker fee), taken
  from each trade's R on its entry and exit prices;
- the floor is H-AR's in cost terms: the stop at least 10 round trips of fee (2% of the entry), in place of 10 spreads;
- stop slippage: 1 basis point of the market's median close over the export;
- signals from 2021-10-03 (H-AS's start; the data begins 2021-01-01) to the export's end.

    python -m algo_research.search_ladder_crypto run --registered
    python -m algo_research.search_ladder_crypto verdict
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import zlib

import numpy as np
import pandas as pd

from agent.brokers.fill_model import FillModel
from algo_research.search_ladder import MIN_SPREADS, NY, OUT, SEED, SNAPSHOTS, price, signals
from algo_research.search_ladder_assets import verdict
from thesis_engine.replay import prepare
from thesis_engine.settings import V1

__all__ = ["MARKETS", "run_market", "fee_r"]

MARKETS = {"BTCUSD": "crypto", "ETHUSD": "crypto", "XRPUSD": "crypto"}
SNAPSHOT = "binance-m1-crypto"
SIGNALS_FROM = "2021-10-03"
FEE = 0.001                 # a side, of the notional
FLOOR_ROUND_TRIPS = 10.0    # the stop is at least this many round trips of fee
SLIPPAGE_BP = 1.0           # stop slippage, basis points of the median close
ARMS = ("BASE_FULL", "BASE_HALF")


def fee_r(rec: dict, side: int) -> float:
    """The fee on entry and exit in R: the exit price is the fill moved by the trade's own R (before the fee)."""
    exit_ = rec["fill"] + side * rec["net_r"] * rec["risk"]
    return FEE * (rec["fill"] + exit_) / rec["risk"]


def floor_ok(rec: dict) -> bool:
    return rec["risk"] >= FLOOR_ROUND_TRIPS * 2 * FEE * rec["fill"]


def run_market(market: str) -> tuple[list, dict]:
    m1 = pd.read_parquet(SNAPSHOTS / SNAPSHOT / f"{market}_M1.parquet")
    m1 = m1.sort_values("time", kind="stable").reset_index(drop=True)
    sigs = signals(m1, market, int(pd.Timestamp(SIGNALS_FROM).value // 10**9))
    mk = prepare(market, m1, V1)
    # H-AR's floor (MIN_SPREADS x typical spread) set to half the fee floor at the window's lowest close, so it only
    # drops stops the fee floor below drops too; the fee floor itself is applied after pricing.
    low = float(np.min(m1["close"].to_numpy(dtype=float)))
    mk = dataclasses.replace(mk, typical_spread=0.5 * FLOOR_ROUND_TRIPS * 2 * FEE * low / MIN_SPREADS)
    slip = SLIPPAGE_BP / 1e4 * float(np.median(m1["close"].to_numpy(dtype=float)))
    fm = FillModel(slip)
    first = int(np.searchsorted(mk.t, pd.Timestamp(SIGNALS_FROM, tz=NY).tz_convert("UTC").value, "left"))
    trades, floored = [], 0
    for arm in ARMS:
        half = arm.endswith("HALF")
        for tf, lst in sigs.items():
            rng = np.random.default_rng(zlib.crc32(f"H-AT|{SEED}|{market}|{arm}|{tf}".encode()))
            busy = busy_p = -1
            for n, sg in enumerate(lst):
                if sg["t0"] < busy:
                    continue
                rec, why = price(mk, fm, f"{market}-{arm}-{tf}-{n}", sg["t0"], sg["until"], sg["side"], sg["stop"],
                                 sg["own"], sg["d1"], half)
                if rec is None:
                    floored += why == "FLOOR"
                    continue
                if not floor_ok(rec):
                    floored += 1
                    continue
                busy = rec["closed_at"]
                rec = {**rec, "fee_r": fee_r(rec, sg["side"])}
                rec["net_r"] = rec["net_r"] - rec["fee_r"]
                base = {"market": market, "class": MARKETS[market], "arm": arm, "tf": tf, "side": sg["side"]}
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
                if prec is not None and floor_ok(prec):
                    busy_p = prec["closed_at"]
                    prec = {**prec, "fee_r": fee_r(prec, sg["side"])}
                    prec["net_r"] = prec["net_r"] - prec["fee_r"]
                    trades.append({**base, "placebo": True, "t_place": tp, **prec})
    return trades, {"since": SIGNALS_FROM, "stop_slippage": slip, "floored": floored,
                    "signals": {tf: len(v) for tf, v in sigs.items()}}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m algo_research.search_ladder_crypto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--registered", action="store_true", help="H-AT is registered and committed")
    sub.add_parser("verdict")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    markets = list(MARKETS)
    if args.cmd == "run":
        if not args.registered:
            raise SystemExit("H-AT runs once, after its registration is committed (--registered)")
        rows, info, t0 = [], {}, time.time()
        for m in markets:
            tr, meta = run_market(m)
            rows += tr
            info[m] = meta
            print(f"{m}: {sum(not x['placebo'] for x in tr)} real trades, {meta['floored']} under the fee floor "
                  f"({time.time() - t0:.0f}s)", flush=True)
        pd.DataFrame(rows).to_parquet(OUT / "hat_crypto.parquet")
        (OUT / "hat_crypto_info.json").write_text(json.dumps({"markets": info}, indent=1), encoding="utf-8")
    else:
        df = pd.read_parquet(OUT / "hat_crypto.parquet")
        res = verdict(df, markets)
        (OUT / "hat_crypto_verdict.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
