"""The Thesis Engine on the terminal's live bars, on paper (thesis-engine Requirement 14, task 416).

Each cycle reads the trader's /context calls. For each market with a call live now (or one that ended within the
last day), it runs the machine over the terminal's closed M1 from ``WARMUP_DAYS`` ago to the last closed minute. The
machine is a fold over closed candles, so running it from the start each cycle is the same as stepping it forward:
a restart is a replay (Property 1), and each cycle's journal extends the last one's. Orders are paper, through the
shared fill model on the terminal's bars. Nothing is sent to the broker, and a market without a live call isn't
read at all: with no thesis, the engine is FLAT.

    python -m thesis_engine live [--once] [--every 300]
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from agent.context_calls import CALLS_FILE
from thesis_engine.replay import prepare, run
from thesis_engine.settings import V1, Settings
from thesis_engine.thesis import call_theses

__all__ = ["MARKETS", "Terminal", "Runner", "main"]

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "research" / "thesis_engine" / "live"
MARKETS = ("XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
WARMUP_DAYS = 150
NY = "America/New_York"


def _ny(ns: Optional[int]) -> str:
    return "-" if ns is None else pd.Timestamp(int(ns), tz="UTC").tz_convert(NY).strftime("%a %d %b %H:%M")


class Terminal:
    """The broker's terminal, read only: closed M1 bars (spread in price units), a month at a time."""

    def __init__(self, profile: str = "exness-standard-swapfree") -> None:
        import MetaTrader5 as mt5
        from agent.broker_profiles import load_profile
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        self.mt5, self.profile = mt5, load_profile(profile)

    def m1(self, market: str, start: datetime, end: datetime) -> pd.DataFrame:
        mt5, symbol = self.mt5, self.profile.symbol(market)
        mt5.symbol_select(symbol, True)
        point = mt5.symbol_info(symbol).point
        parts, cursor = [], start
        while cursor < end:
            upto = min(cursor + timedelta(days=31), end)
            rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, cursor, upto)
            if rates is not None and len(rates):
                parts.append(pd.DataFrame(rates))
            cursor = upto
        if not parts:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"])
        f = pd.concat(parts, ignore_index=True).drop_duplicates("time")
        return pd.DataFrame({"time": pd.to_datetime(f["time"], unit="s", utc=True),
                             **{k: f[k].astype(float) for k in ("open", "high", "low", "close")},
                             "spread": f["spread"].astype(float) * point})


@dataclass
class Runner:
    """One cycle at a time; the M1 read so far is kept per market, so a cycle reads only the new minutes."""
    bars: Callable[[str, datetime, datetime], pd.DataFrame]
    calls: Path = CALLS_FILE
    out: Path = OUT
    s: Settings = V1
    slippage: Dict[str, float] = field(default_factory=dict)
    _m1: Dict[str, pd.DataFrame] = field(default_factory=dict)
    _seen: Dict[str, int] = field(default_factory=dict)

    def _closed_m1(self, market: str, now: datetime) -> pd.DataFrame:
        have = self._m1.get(market)
        start = now - timedelta(days=WARMUP_DAYS) if have is None or have.empty else \
            have["time"].iloc[-1].to_pydatetime() + timedelta(minutes=1)
        new = self.bars(market, start, now)
        both = new if have is None else pd.concat([have, new], ignore_index=True)
        both = both.drop_duplicates("time").sort_values("time").reset_index(drop=True)
        both = both[both["time"] >= pd.Timestamp(now - timedelta(days=WARMUP_DAYS))]
        closed = both[both["time"] + pd.Timedelta(minutes=1) <= pd.Timestamp(now)]   # never the forming minute
        self._m1[market] = closed
        return closed

    def cycle(self, now: Optional[datetime] = None) -> List[dict]:
        """Each market's state now, with what changed since the last cycle."""
        now = now or datetime.now(timezone.utc)
        t = int(pd.Timestamp(now).value)
        out = []
        for market in MARKETS:
            theses = [th for th in call_theses(market, self.calls) if th.until > t - 86400 * 10**9 and th.since <= t]
            if not theses:
                out.append({"market": market, "state": "FLAT", "why": "no call live: with no thesis nothing runs",
                            "new": [], "trades": []})
                continue
            m1 = self._closed_m1(market, now)
            j = run(prepare(market, m1, self.s), theses, self.s, slippage=self.slippage.get(market, 0.0))
            j.write(self.out / f"{market}.jsonl")
            moves = j.of("transition")
            new = moves[self._seen.get(market, 0):]
            self._seen[market] = len(moves)
            last = moves[-1] if moves else None
            out.append({"market": market, "state": last["to"] if last else "FLAT",
                        "why": last["reason"] if last else "no move yet",
                        "new": [(m["t"], m["frm"], m["to"], m["reason"]) for m in new],
                        "trades": [{k: tr[k] for k in ("direction", "fill", "stop", "target", "reason", "net_r",
                                                      "filled_at", "closed_at")} for tr in j.of("trade")],
                        "theses": [(th.side, th.draw, th.protected, th.since, th.until) for th in theses]})
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "status.json").write_text(json.dumps({"at": now.isoformat(timespec="seconds"), "markets": out},
                                                         indent=1, default=str), encoding="utf-8")
        return out


def _print(rows: List[dict], first: bool) -> None:
    for r in rows:
        if first:
            print(f"{r['market']:7} {r['state']:9} {r['why']}")
        for t, a, b, why in ([] if first else r["new"]):
            print(f"{_ny(t)}  {r['market']:7} {a} -> {b}: {why}")
    print(flush=True)


def main(once: bool = False, every: int = 300) -> None:
    from agent.broker_profiles import load_profile
    specs = load_profile("exness-standard-swapfree").specs()
    terminal = Terminal()
    runner = Runner(terminal.m1, slippage={m: specs[m].stop_slippage for m in MARKETS})
    print(f"The Thesis Engine on the terminal, paper only. Calls from {runner.calls}; journals in {runner.out}.")
    first = True
    while True:
        rows = runner.cycle()
        print(datetime.now().strftime("%H:%M:%S"), flush=True)
        _print(rows, first)
        first = False
        if once:
            return
        time.sleep(every)
