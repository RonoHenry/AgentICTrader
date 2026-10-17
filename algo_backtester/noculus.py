"""Noculus: the trader's marks and trades against the engine's (algo-backtester update 2026-10-16).

The charts app is Noculus (D30), and its Engine mode is the engine watch (``watch.py``). A watch session started
blind withholds the engine's layers until the trader reveals them (D27). Meanwhile the trader marks PD arrays by
their candles and places pseudo trades, at the replay clock. Each blind session keeps its own journal:

    data/journal/noculus/<instrument>/<session>.json     {"session", "marks", "trades", "reveal", "comparison"}

It is local and git-ignored, and written whole through a temporary file after every change.

A mark is read from the candles the trader clicked, on bars that closed by the replay clock (Requirement 18):

- **FVG** — its third candle, C1 two before. Bullish when C3's low is above C1's high: the gap runs from C1's
  high to C3's low, and ``mid`` is the CE. Bearish is the mirror. Three candles without a gap are refused.
  This is ``algo_research.atlas.arrays.fvgs`` read from a click instead of from the bars (AR-D27).
- **IFVG** — the same three candles, plus the first later close of that timeframe beyond the gap's far edge. It
  carries the gap's zone, facing the other way. Before that close it is still an FVG, and the mark is refused.
- **Order block** — the block's own candle: its high to low, ``mid`` the midpoint of its body (the MT). The
  direction is the trader's, and defaults to the opposite of the candle's colour.
- **Breaker** — an order-block candle plus the first later close beyond it, facing the other way.

``formed_at`` is always the close that made the mark: C3's for a gap, the flipping candle's for an inversion.
Nothing is read from a candle that has not closed by the clock, so a mark holds only what the trader could see.

A pseudo trade is placed at the clock and plays out as it advances (Requirement 19), priced by AlgoResearch's
race rules (its Requirement 7, which Property 5 checks against the shared fill model): bid and ask, each bar's
spread floored at the typical spread, the stop worsened by the spec's slippage, a bar opening beyond the stop
exiting at its open, and the stop winning a bar that reaches both. A market order fills at the next M1 bar's
ask (LONG) or bid (SHORT); a limit sits until its expiry and fills at its own price on the first bar whose
entry side trades through it. ``settle`` reads only bars closed by the clock, so a trade seen at the clock is
what the trader would have had; ``close`` exits at the last such close, on the side that closes the position.

    place(body, path, clock)                 # the ticket, validated against the price at the clock
    settle(trade, path, clock, costs)         # advance it: PENDING -> OPEN -> CLOSED, or EXPIRED / REJECTED
    close(trade, path, clock, costs)          # the trader's own exit

``path`` is the session's M1, in New York wall seconds: {time, open, high, low, close, spread}, the prices bid.

Validates: Requirements 17.4, 18.1-18.3, 19.1-19.3 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from algo_backtester.config import REPO_ROOT
from algo_research.replay.timeframes import seconds_of

__all__ = ["MARK_TOOLS", "NOCULUS_DIR", "NoculusJournal", "build_mark", "close", "place", "settle"]

#: Where the sessions' journals live (local, git-ignored).
NOCULUS_DIR = REPO_ROOT / "data" / "journal" / "noculus"
#: The tools the trader marks with (Requirement 18.1).
MARK_TOOLS = ("FVG", "IFVG", "OB", "BRK")
_KEYS = ("session", "marks", "trades", "reveal", "comparison")


class NoculusJournal:
    """One blind session's journal: its marks, trades, reveal and comparison."""

    def __init__(self, path: Path, session: Optional[dict] = None) -> None:
        self.path = Path(path)
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"session": dict(session or {}), "marks": [], "trades": [], "reveal": None, "comparison": None}
        for key in _KEYS:
            self.data.setdefault(key, [] if key in ("marks", "trades") else None)

    def save(self) -> None:
        """Write the whole journal through a temporary file, so a crash never leaves half of it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # ── the trader's marks (Requirement 18) ─────────────────────────────────
    def add_mark(self, mark: dict) -> dict:
        """Keep a mark, numbered in the order it was made."""
        row = {"id": f"m{len(self.data['marks']) + 1}", **mark, "deleted_at": None}
        self.data["marks"].append(row)
        self.save()
        return row

    def delete_mark(self, mark_id: str, clock: int) -> dict:
        """Mark one as deleted, at the clock. It stays in the journal (Requirement 18.3)."""
        for row in self.data["marks"]:
            if row["id"] == mark_id:
                row["deleted_at"] = int(clock)
                self.save()
                return row
        raise KeyError(f"no mark {mark_id} in this session")

    # ── the trader's trades (Requirement 19) ────────────────────────────────
    def add_trade(self, trade: dict) -> dict:
        """Keep a trade, numbered in the order it was placed."""
        row = {"id": f"t{len(self.data['trades']) + 1}", **trade}
        self.data["trades"].append(row)
        self.save()
        return row

    def trade(self, trade_id: str) -> dict:
        for row in self.data["trades"]:
            if row["id"] == trade_id:
                return row
        raise KeyError(f"no trade {trade_id} in this session")


def _closed_bars(bars: pd.DataFrame, tf: str, clock: int) -> tuple[np.ndarray, tuple[np.ndarray, ...], int]:
    """The ``tf`` bars closed by ``clock``, and how many of them there are."""
    t = np.asarray(bars["time"], dtype=np.int64)
    n = int(np.count_nonzero(t + seconds_of(tf) <= clock))
    return t, tuple(np.asarray(bars[k], dtype=float) for k in ("open", "high", "low", "close")), n


def _clicked(t: np.ndarray, n: int, tf: str, candle: int) -> int:
    """Where the clicked candle sits among the closed bars, or why it cannot be used."""
    hit = np.flatnonzero(t == candle)
    if not len(hit):
        raise ValueError(f"no {tf} candle starts at {candle}")
    if int(hit[0]) >= n:
        raise ValueError(f"that {tf} candle has not closed by the clock")
    return int(hit[0])


def _beyond(close: np.ndarray, n: int, start: int, level: float, below: bool, tf: str, still: str) -> int:
    """The first closed bar after ``start`` whose close is beyond ``level``, or a refusal."""
    segment = close[start + 1:n]
    hits = segment < level if below else segment > level
    if not hits.any():
        raise ValueError(f"no {tf} close beyond it yet: it is still {still}")
    return start + 1 + int(np.argmax(hits))


def build_mark(bars: pd.DataFrame, *, tool: str, tf: str, clock: int, candle: int,
               direction: Optional[int] = None, note: str = "") -> dict:
    """One mark from the candles clicked on ``tf``, read only from bars closed by ``clock``.

    ``bars`` are that timeframe's bars as the chart draws them (columns time — the bar's start in New York wall
    seconds — open, high, low, close). ``candle`` is the clicked bar's start: C3 for a gap, the block's candle
    for an order block. A mark that would need a candle closing after the clock is refused, with the reason.
    """
    tool, tf, clock, candle = str(tool).upper(), str(tf), int(clock), int(candle)
    if tool not in MARK_TOOLS:
        raise ValueError(f"tool: one of {', '.join(MARK_TOOLS)}")
    size = seconds_of(tf)                                       # also refuses a timeframe the charts don't keep
    t, (o, h, l, c), n = _closed_bars(bars, tf, clock)
    i = _clicked(t, n, tf, candle)
    if tool in ("FVG", "IFVG"):
        if i < 2:
            raise ValueError(f"an FVG needs the two candles before C3: there are none before {candle}")
        if l[i] > h[i - 2]:
            facing, low, high = 1, float(h[i - 2]), float(l[i])
        elif h[i] < l[i - 2]:
            facing, low, high = -1, float(h[i]), float(l[i - 2])
        else:
            raise ValueError(f"those three {tf} candles leave no gap")
        mid, formed, clicked = (low + high) / 2, int(t[i]) + size, [int(t[i - 2]), int(t[i - 1]), int(t[i])]
        if tool == "IFVG":                                      # the gap, read the other way after a close beyond
            j = _beyond(c, n, i, low if facing == 1 else high, facing == 1, tf, "an FVG")
            facing, formed, clicked = -facing, int(t[j]) + size, [*clicked, int(t[j])]
    else:
        facing = int(direction) if direction else (-1 if c[i] > o[i] else 1)   # the opposite of the candle's colour
        low, high = float(l[i]), float(h[i])
        mid, formed, clicked = (float(o[i]) + float(c[i])) / 2, int(t[i]) + size, [int(t[i])]
        if tool == "BRK":
            j = _beyond(c, n, i, low if facing == 1 else high, facing == 1, tf, "an order block")
            facing, formed, clicked = -facing, int(t[j]) + size, [*clicked, int(t[j])]
    return {"tool": tool, "tf": tf, "direction": int(facing), "low": low, "high": high, "mid": mid,
            "formed_at": formed, "candles": clicked, "clock": clock, "note": str(note or "")[:1000]}


# ── pseudo trades (Requirement 19) ───────────────────────────────────────────
#: What the trader may place.
DIRECTIONS, KINDS = ("LONG", "SHORT"), ("MARKET", "LIMIT")
#: A trade is settled no further than the last M1 bar closed by the clock.
_M1 = 60


def _closed(path: Mapping[str, np.ndarray], clock: int) -> int:
    """How many M1 bars have closed by ``clock``."""
    return int(np.count_nonzero(np.asarray(path["time"], dtype=np.int64) + _M1 <= int(clock)))


def place(body: dict, path: Mapping[str, np.ndarray], clock: int, until: Optional[int] = None) -> dict:
    """The trader's ticket at the clock: LONG or SHORT, market or limit, with a stop and a target.

    It is checked against the price at the clock, as a broker would: a limit sits on its own side of the market,
    and the stop and the target on their own sides of the entry. ``until`` is the expiry a limit takes when the
    trader names none — the session's end.
    """
    direction = str(body.get("direction", "")).upper()
    kind = str(body.get("kind", "MARKET")).upper()
    if direction not in DIRECTIONS:
        raise ValueError("direction: LONG or SHORT")
    if kind not in KINDS:
        raise ValueError("kind: MARKET or LIMIT")
    clock, n = int(clock), _closed(path, clock)
    if not n:
        raise ValueError("no M1 bar has closed by the clock yet")
    long_ = direction == "LONG"
    bid = float(path["close"][n - 1])
    ask = bid + float(path["spread"][n - 1])
    stop, target = float(body["stop"]), float(body["target"])
    price, expiry = body.get("price"), body.get("expiry")
    if kind == "LIMIT":
        if price is None:
            raise ValueError("price: a limit order needs one")
        price = float(price)
        if long_ and price >= ask:
            raise ValueError(f"price: a LONG limit sits below the ask ({ask:.5f})")
        if not long_ and price <= bid:
            raise ValueError(f"price: a SHORT limit sits above the bid ({bid:.5f})")
        entry, expiry = price, int(expiry) if expiry else (int(until) if until else None)
    else:
        entry, expiry, price = (ask if long_ else bid), None, None
    if (stop >= entry) if long_ else (stop <= entry):
        raise ValueError(f"stop: {'below' if long_ else 'above'} the entry ({entry:.5f})")
    if (target <= entry) if long_ else (target >= entry):
        raise ValueError(f"target: {'above' if long_ else 'below'} the entry ({entry:.5f})")
    return {"direction": direction, "kind": kind, "price": price, "stop": stop, "target": target, "expiry": expiry,
            "mark": str(body.get("mark") or "") or None, "placed_at": clock, "note": str(body.get("note") or "")[:1000],
            "state": "PENDING", "fill": None, "fill_bid": None, "filled_at": None, "exit": None, "exit_bid": None,
            "exit_at": None, "outcome": None, "risk": None, "gross_r": None, "net_r": None, "commission_r": None,
            "mfe_r": None, "mae_r": None, "live_r": None, "ambiguous": False, "settled_to": clock}


def _fill(trade: dict, path: Mapping[str, np.ndarray], n: int, long_: bool) -> Optional[int]:
    """Fill the trade if its entry has come by the clock, and give the bar it filled on.

    A market order takes the first bar opening at or after the order: the ask for LONG, the bid for SHORT, which
    is the race's own entry (AlgoResearch Requirement 7.1). A limit takes its own price on the first bar whose
    entry side trades through it: the ask low for LONG, the bid high for SHORT.
    """
    t, o, h, l, sp = (np.asarray(path[k]) for k in ("time", "open", "high", "low", "spread"))
    i0 = int(np.searchsorted(t.astype(np.int64), trade["placed_at"], "left"))
    if trade["kind"] == "MARKET":
        if i0 >= n:
            return None                                             # the entry bar has not closed yet
        fill = float(o[i0]) + float(sp[i0]) if long_ else float(o[i0])
        if (fill <= trade["stop"] or fill >= trade["target"]) if long_ else (fill >= trade["stop"] or fill <= trade["target"]):
            trade.update(state="REJECTED", outcome="REJECTED")      # the entry is already past the stop or target
            return None
        bar, fill_bid = i0, float(o[i0])
    else:
        price = float(trade["price"])
        gone = int(np.searchsorted(t.astype(np.int64), trade["expiry"], "left")) if trade["expiry"] else len(t)
        end = min(n, gone)
        through = (l[i0:end] + sp[i0:end] <= price) if long_ else (h[i0:end] >= price)
        if not through.any():
            if n >= gone:
                trade.update(state="EXPIRED", outcome="EXPIRED")    # the expiry passed with the price never there
            return None
        bar = i0 + int(np.argmax(through))
        fill, fill_bid = price, (price - float(sp[bar]) if long_ else price)
    trade.update(fill=fill, fill_bid=fill_bid, filled_at=int(t[bar]), state="OPEN", risk=abs(fill - trade["stop"]))
    return bar


def settle(trade: dict, path: Mapping[str, np.ndarray], clock: int, costs=None) -> dict:
    """Advance the trade to the clock, reading no bar that closes after it (Requirement 19.2)."""
    clock = int(clock)
    if trade["state"] in ("CLOSED", "EXPIRED", "REJECTED"):
        return trade
    trade["settled_to"] = clock
    n = _closed(path, clock)
    long_ = trade["direction"] == "LONG"
    bar = _fill(trade, path, n, long_) if trade["filled_at"] is None else \
        int(np.searchsorted(np.asarray(path["time"], dtype=np.int64), trade["filled_at"], "left"))
    if bar is None or n <= bar:
        return trade
    o, h, l, c, sp = (np.asarray(path[k], dtype=float) for k in ("open", "high", "low", "close", "spread"))
    t = np.asarray(path["time"], dtype=np.int64)
    stop, target, fill, fill_bid = trade["stop"], trade["target"], trade["fill"], trade["fill_bid"]
    risk, sign = trade["risk"], 1.0 if long_ else -1.0
    closing0 = fill_bid if long_ else fill_bid + float(sp[bar])      # where the position would close at the fill
    window = slice(bar, n)
    if long_:
        adverse, favourable = l[window], h[window]
        stop_hit, target_hit = adverse <= stop, favourable >= target
    else:
        adverse, favourable = h[window] + sp[window], l[window] + sp[window]
        stop_hit, target_hit = adverse >= stop, favourable <= target
    hits = stop_hit | target_hit
    pick_adverse, pick_favourable = (min, max) if long_ else (max, min)
    if not hits.any():                                              # still open: its live R at the last close
        mae = pick_adverse(closing0, float(adverse.min() if long_ else adverse.max()))
        mfe = pick_favourable(closing0, float(favourable.max() if long_ else favourable.min()))
        live = float(c[n - 1]) if long_ else float(c[n - 1]) + float(sp[n - 1])
        trade.update(live_r=sign * (live - fill) / risk, mfe_r=sign * (mfe - fill) / risk,
                     mae_r=sign * (mae - fill) / risk)
        return trade
    j = int(np.argmax(hits))
    at = bar + j
    before_adverse, before_favourable = adverse[:j], favourable[:j]
    first_adverse = [float(before_adverse.min() if long_ else before_adverse.max())] if j else []
    first_favourable = [float(before_favourable.max() if long_ else before_favourable.min())] if j else []
    if stop_hit[j]:
        outcome, ambiguous = "STOP", bool(target_hit[j])            # a bar reaching both is the stop's
        closing_open = float(o[at]) if long_ else float(o[at]) + float(sp[at])
        gapped = closing_open < stop if long_ else closing_open > stop
        market = closing_open if gapped else stop                   # a bar opening beyond the stop exits at its open
        slippage = costs.stop_slippage if costs else 0.0
        exit_price = market - slippage if long_ else market + slippage
        exit_bid = market if long_ else market - float(sp[at])
        mae = pick_adverse(closing0, market, *first_adverse)
        mfe = pick_favourable(closing0, float(favourable[j]), *first_favourable)
    else:
        outcome, ambiguous = "TARGET", False
        exit_price = target
        exit_bid = target if long_ else target - float(sp[at])
        mae = pick_adverse(closing0, float(adverse[j]), *first_adverse)
        mfe = pick_favourable(closing0, target, *first_favourable)
    _settled(trade, outcome, exit_price, exit_bid, int(t[at]), sign, costs, ambiguous=ambiguous)
    trade.update(mfe_r=sign * (mfe - fill) / risk, mae_r=sign * (mae - fill) / risk)
    return trade


def _settled(trade: dict, outcome: str, exit_price: float, exit_bid: float, exit_at: int, sign: float,
             costs, ambiguous: bool = False) -> None:
    """Close the trade's books: R on the executed prices, gross on the bid, less commission (AR task 201)."""
    fill, risk = trade["fill"], trade["risk"]
    commission = costs.commission_r(fill, exit_price, risk) if costs and costs.commission_r else 0.0
    trade.update(state="CLOSED", outcome=outcome, exit=float(exit_price), exit_bid=float(exit_bid),
                 exit_at=int(exit_at), ambiguous=bool(ambiguous), commission_r=float(commission), live_r=None,
                 gross_r=sign * (exit_bid - trade["fill_bid"]) / risk,
                 net_r=sign * (exit_price - fill) / risk - commission)


def close(trade: dict, path: Mapping[str, np.ndarray], clock: int, costs=None) -> dict:
    """The trader's own exit, at the last M1 close by the clock, on the side that closes it (Requirement 19.3)."""
    settle(trade, path, clock, costs)                               # it may have reached the stop or target first
    if trade["state"] == "PENDING":
        raise LookupError("that trade has not filled: there is nothing to close")
    if trade["state"] != "OPEN":
        return trade
    n = _closed(path, clock)
    long_ = trade["direction"] == "LONG"
    last = n - 1
    exit_bid = float(path["close"][last])
    exit_price = exit_bid if long_ else exit_bid + float(path["spread"][last])
    _settled(trade, "MANUAL", exit_price, exit_bid, int(path["time"][last]) + _M1, 1.0 if long_ else -1.0, costs)
    return trade
