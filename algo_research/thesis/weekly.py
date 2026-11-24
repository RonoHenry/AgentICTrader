"""H-AV: a language model reads the /weekly blind charts with AlgoMindDIS's map and calls the next week.

The trader's blind weekly calls (``algo_research.replay.weekly``, Requirement 36) are measured on charts nobody
has read with these rules: one market-week of Yahoo's daily history 1996-2017, the market hidden, the dates moved,
the prices scaled so the last close is 1000. H-AV gives the same charts to a language model, in the same order,
with AlgoMindDIS v1's map at that Friday's close (structure, dealing ranges, delivery, the untaken liquidity on both
sides and the arrays in play) as the map-maker, and lets the model be the compass: it names the side, the draw and
the protected swing, or makes no call. Its calls go through ``WeeklyApp.call`` into their own journal, so they are
scored exactly as the trader's are: the next week against the market's drift, and H-AE's race against its control.

Nothing real reaches the model: no market name, no date (the D1 rows carry only the weekday), no unscaled price, and
none of AlgoMindDIS's own verdict (its scores, state, side, draw, protected level, narrative or evidence votes).
The instructions are generic ICT; nothing from the trader's journal or method goes out (free endpoints may log).

    python -m algo_research.thesis.weekly run [--model M] [--first 0] [--count 300] [--max-calls 300]
    python -m algo_research.thesis.weekly summary [--model M]
    python -m algo_research.thesis.weekly show N        # the facts for chart N, as sent (no call, no score)
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from algo_backtester.config import REPO_ROOT
from algo_research.replay.weekly import EVIDENCE, LAST, WeeklyApp
from algo_research.search_narrative import ADR_N
from algo_research.thesis.prompt import _last_object

__all__ = ["MODEL", "SYSTEM", "Call", "MapMaker", "facts", "parse_call", "run", "summary", "verdict"]

ROOT = REPO_ROOT / "data" / "research" / "hav"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
FIRST, COUNT = 0, 300
SHOW = {"MN1": 24, "W1": 26, "D1": 30}
TOP_OBJECTIVES = 4
NEAREST = 3
MAX_ARRAYS = 8
MIN_SIDED = 100
BAR = 0.57
_DAY = 86_400 * 10**9
_WEEKDAY = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_CONFIDENCE = {"low": 1, "medium": 2, "high": 3}

SYSTEM = """You are a price-action analyst who reads markets with ICT concepts, top-down: monthly, weekly, then daily.
It is Friday's close. Call next week's direction from the facts given, or decide there is no call.

How to read:
- The draw on liquidity first: price is drawn to old highs and lows, equal highs and lows, and unfilled fair value
  gaps. Name the draw the market is most likely to reach next; the side follows from it.
- Each timeframe: where price sits in its dealing range (premium above equilibrium, discount below), its structure
  (breaks of swing highs and lows), and its delivery phase: consolidation, expansion, retracement or reversal.
- The candle lens on W1 and D1: did the last candle take the previous candle's high or low and close back inside
  (a turtle soup) or close beyond it (displacement)? Bodies against wicks.
- Higher timeframes weigh more. A week often makes its false move against the draw early (Monday to Wednesday)
  before it expands toward the draw.
- The AlgoMindDIS map lists each timeframe's structure, range and delivery, the liquidity on both sides and the
  arrays in play. It is a map, not a call: you decide the side.
- "none" is a valid answer when the timeframes conflict or the draw is unclear. Being wrong costs money; no call
  costs nothing.

Use only the facts given. The market and the dates are hidden; prices are rescaled so the last close is 1000.00.

Answer with one JSON object and nothing after it:
{"bias": "bullish" | "bearish" | "none",
 "draw": the price you expect to be reached (above 1000 when bullish, below when bearish; null when none),
 "protected": the swing whose break on a daily close would prove the call wrong (below 1000 when bullish, above
              when bearish; null when none),
 "confidence": "low" | "medium" | "high",
 "evidence": a list of tags taken only from: """ + json.dumps(list(EVIDENCE)) + """,
 "reason": "two or three sentences: the draw, the timeframes that agree, what you expect first"}"""


# ── the map ───────────────────────────────────────────────────────────────────

class MapMaker:
    """AlgoMindDIS v1's analyzers on one market, prepared once over its daily history. Every prepared read is dated,
    so ``observe`` at a Friday sees only what was complete by that close (``algomind_dis.observe``)."""

    def __init__(self, market: str, days: pd.DataFrame) -> None:
        from algomind_dis.frames import from_daily                       # noqa: PLC0415
        from algomind_dis.observe import prepare                         # noqa: PLC0415
        from algomind_dis.settings import V1                             # noqa: PLC0415
        self.market, self.s = market, V1
        self.frames = from_daily(market, days)
        self.prepared = prepare(market, self.frames.full, V1)

    def at(self, friday: pd.Timestamp):
        """The observation at the Friday close (the D1 candle dated Friday ends at Saturday 00:00 UTC)."""
        from algomind_dis.observe import observe                         # noqa: PLC0415
        t = int(pd.Timestamp(friday, tz="UTC").value) + _DAY
        frames = self.frames.at(t)
        return observe(self.market, frames, self.s, self.prepared), frames


def _p(x: float, k: float) -> str:
    return f"{x * k:.2f}"


def _row(b: dict) -> str:
    return f"{b['open']:.2f} {b['high']:.2f} {b['low']:.2f} {b['close']:.2f}"


def facts(app: WeeklyApp, makers: dict, n: int, maker: Callable[[str, pd.DataFrame], MapMaker] = MapMaker) -> str:
    """Chart ``n`` as the model reads it: the chart's own scaled candles and AlgoMindDIS's map, blind."""
    item = app.key(n)
    m, w = app._item(item)
    end = int(m.w1["end"].iloc[w])
    close = float(m.cl[end])
    k = LAST / close
    chart = app.chart({"id": n})["bars"]
    if m.name not in makers:
        makers[m.name] = maker(m.name, app.loader(m.name))
    obs, frames = makers[m.name].at(pd.Timestamp(m.d1["date"].iloc[end]))
    if not np.isclose(obs.price, close, rtol=1e-9, atol=1e-12):
        raise RuntimeError(f"chart {n}: the map's close {obs.price} is not the chart's {close}")
    adr = float(m.adr[end]) * k if np.isfinite(m.adr[end]) else float("nan")

    out = ["FRIDAY CLOSE. Prices are rescaled: the last close is 1000.00.",
           f"One average daily range (ADR, {ADR_N} days) is {adr:.1f} points." if np.isfinite(adr) else "",
           "", "CANDLES, oldest first (open high low close):"]
    mn1 = chart["MN1"][-SHOW["MN1"]:]
    out.append(f"MN1, the last {len(mn1)} months (the last month is still forming, up to this Friday):")
    out += [f"  {_row(b)}" for b in mn1]
    w1 = chart["W1"][-SHOW["W1"]:]
    out.append(f"W1, the last {len(w1)} weeks (the last week closed this Friday):")
    out += [f"  {_row(b)}" for b in w1]
    d1 = chart["D1"][-SHOW["D1"]:]
    out.append(f"D1, the last {len(d1)} days (weekday, then open high low close):")
    out += [f"  {_WEEKDAY[int(pd.Timestamp(b['time']).dayofweek)]} {_row(b)}" for b in d1]

    out += ["", "ALGOMINDDIS MAP at this close (MN1, W1 and D1 count only closed candles):"]
    for tf in ("MN1", "W1", "D1"):
        ctx = obs.contexts.get(tf)
        if ctx is None:
            continue
        line = f"{tf}: structure {ctx.structural_direction}"
        if ctx.delivery is not None:
            line += f"; delivery {ctx.delivery.state} ({ctx.delivery.direction})"
        swing = next(((r, p) for r, p in zip(ctx.ranges, ctx.positions) if r.kind == "SWING"), None)
        if swing is not None:
            r, p = swing
            line += (f"; swing range {_p(r.low, k)}-{_p(r.high, k)}, equilibrium {_p(p.equilibrium, k)}, "
                     f"price at {100 * p.position:.0f}% ({p.zone})")
        out.append(line)

    from algomind_dis.analyzers.objectives import ranked                   # noqa: PLC0415
    for side, words in (("BULLISH", "above"), ("BEARISH", "below")):
        live = ranked(obs.objectives, side)
        top = live[:TOP_OBJECTIVES]
        near = [o for o in sorted(live, key=lambda o: abs(o.price - close)) if o not in top][:NEAREST]
        out.append(f"Untaken liquidity {words}, most significant first:" if top else f"Untaken liquidity {words}: none listed")
        out += [f"  {o.tf} {o.source} at {_p(o.price, k)} ({o.kind}, {o.status}, significance {o.significance:.2f})"
                for o in top]
        if near:
            out.append(f"  and the nearest others {words}:")
            out += [f"  {o.tf} {o.source} at {_p(o.price, k)} ({o.kind}, {o.status}, significance {o.significance:.2f})"
                    for o in near]

    d1c = frames["D1"]
    arrays = [a for c in obs.contexts.values() for a in c.arrays]
    arrays.sort(key=lambda a: abs((a.low + a.high) / 2 - close))
    out.append("Arrays in play (nearest first):" if arrays else "Arrays in play: none")
    for a in arrays[:MAX_ARRAYS]:
        age = int((d1c.end > a.formed_at).sum())
        out.append(f"  {a.tf} {a.direction} {a.kind} {_p(a.low, k)}-{_p(a.high, k)}: price {a.location} it, "
                   f"zone {a.zone or 'n/a'}, displacement {'yes' if a.displacement else 'no'}, "
                   f"after a sweep {'yes' if a.after_sweep else 'no'}, mitigated {'yes' if a.mitigated else 'no'}, "
                   f"formed {age} D1 candles ago")
    return "\n".join(x for x in out if x is not None)


# ── the answer ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Call:
    side: str                        # BULLISH, BEARISH or NONE
    draw: Optional[float]            # chart prices (last close 1000)
    protected: Optional[float]
    confidence: int                  # 1-3, 0 when not given on a NONE
    evidence: tuple[str, ...]
    reason: str

    def body(self, n: int, ms: int) -> dict:
        return {"id": n, "side": self.side, "draw": self.draw, "protected": self.protected,
                "confidence": self.confidence, "evidence": list(self.evidence), "note": self.reason,
                "recognised": False, "ms": ms}


def parse_call(text: str) -> Call:
    """The answer as a /weekly call. Raises ValueError with the reason when it isn't the fixed form."""
    obj = _last_object(text or "")
    if obj is None:
        raise ValueError("no JSON object with a bias")
    bias = str(obj.get("bias", "")).strip().lower()
    reason = re.sub(r"\s+", " ", str(obj.get("reason") or ""))[:1200]
    confidence = _CONFIDENCE.get(str(obj.get("confidence") or "").strip().lower(), 0)
    tags = obj.get("evidence") or []
    evidence = tuple(dict.fromkeys(str(t) for t in tags if str(t) in EVIDENCE)) if isinstance(tags, list) else ()
    if bias in ("none", "neutral"):
        return Call("NONE", None, None, confidence, evidence, reason)
    if bias not in ("bullish", "bearish"):
        raise ValueError(f"bias: bullish, bearish or none, not {bias!r}")
    if not confidence:
        raise ValueError("confidence: low, medium or high")
    try:
        draw, protected = float(obj["draw"]), float(obj["protected"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("a bullish or bearish call needs a numeric draw and protected") from None
    side = 1 if bias == "bullish" else -1
    if not side * (protected - LAST) < 0 < side * (draw - LAST):
        raise ValueError(f"a {bias} call needs its draw {'above' if side > 0 else 'below'} 1000 and its protected "
                         f"swing on the other side (got draw {draw}, protected {protected})")
    return Call("BULLISH" if side > 0 else "BEARISH", draw, protected, confidence, evidence, reason)


# ── the run ───────────────────────────────────────────────────────────────────

def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def app_for(model: str, root: Path = ROOT) -> WeeklyApp:
    return WeeklyApp(Path(root) / _slug(model), reader=False)


def run(model: str = MODEL, first: int = FIRST, count: int = COUNT, max_calls: int = COUNT, root: Path = ROOT,
        client=None, log: Callable[[str], None] = print) -> int:
    """Call charts ``first`` .. ``first + count - 1`` in the /weekly order, skipping those already called. Stops at
    the call budget or when the endpoint keeps refusing (a daily cap): run it again to resume. Returns calls saved."""
    from algo_research.thesis.llm import BudgetExhausted, LLMClient, config_from_env   # noqa: PLC0415
    app = app_for(model, root)
    if client is None:
        client = LLMClient(config_from_env(model=model, max_calls=max_calls,
                                           cache_dir=Path(root) / _slug(model) / "cache"))
    keep = Path(root) / _slug(model) / "facts"
    keep.mkdir(parents=True, exist_ok=True)
    makers: dict = {}
    saved = 0
    for n in range(first, first + count):
        if app.key(n) in app.records():
            continue
        text = facts(app, makers, n)
        (keep / f"{n:04d}.txt").write_text(text, encoding="utf-8")
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]
        started = time.monotonic()
        try:
            reply = client.complete(messages, temperature=0.0)
            try:
                call = parse_call(reply.text)
            except ValueError as first_error:
                again = messages + [{"role": "assistant", "content": reply.text},
                                    {"role": "user", "content": f"That answer is not in the fixed form ({first_error}). "
                                                                "Answer again with the JSON object only."}]
                try:
                    call = parse_call(client.complete(again, temperature=0.0).text)
                except ValueError as second_error:
                    call = Call("NONE", None, None, 0, (), f"UNPARSED: {second_error}")
        except BudgetExhausted as exc:
            log(f"stopped: {exc}")
            break
        except RuntimeError as exc:
            log(f"stopped at chart {n}: {exc}")
            break
        app.call(call.body(n, int(1000 * (time.monotonic() - started))))
        saved += 1
        log(f"chart {n:4d}: {call.side:8s} confidence {call.confidence}  ({len(app.records())} called)")
    return saved


def verdict(s: dict) -> str:
    """H-AV's rule, frozen at registration: at least 100 sided calls, a weekly hit rate of 57% or more, and the 95%
    interval of the excess over drift above zero."""
    week = s.get("week") or {}
    if s.get("sided", 0) < MIN_SIDED:
        return f"TOO FEW CALLS ({s.get('sided', 0)} sided, {MIN_SIDED} needed): fails"
    ok = week.get("hit", 0) >= BAR and (week.get("lo") or -1) > 0
    return "PASSES" if ok else "FAILS"


def summary(model: str = MODEL, root: Path = ROOT) -> dict:
    s = app_for(model, root).summary()
    s["verdict"] = verdict(s) if s.get("calls", 0) >= COUNT else f"running: {s.get('calls', 0)} of {COUNT} charts"
    return s


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--model", default=MODEL)
    r.add_argument("--first", type=int, default=FIRST)
    r.add_argument("--count", type=int, default=COUNT)
    r.add_argument("--max-calls", type=int, default=COUNT)
    s = sub.add_parser("summary")
    s.add_argument("--model", default=MODEL)
    sh = sub.add_parser("show")
    sh.add_argument("n", type=int)
    sh.add_argument("--model", default=MODEL)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.model, a.first, a.count, a.max_calls)
    elif a.cmd == "summary":
        print(json.dumps(summary(a.model), indent=1))
    else:
        print(facts(app_for(a.model), {}, a.n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
