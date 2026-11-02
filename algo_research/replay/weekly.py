"""Blind weekly calls (context-engine Requirement 36): the trader's weekly read, measured on history nobody has
read with these rules.

A chart is one market and one week of Yahoo's daily history (the nine markets), its Friday from 1996 (and the
market's 53rd week) to 2017, in an order fixed by a seed. The page sees MN1, W1 and D1 up to that Friday's close,
with the market hidden, the dates 56 years later (the calendar repeats every 28 years from 1901 to 2099, so weekdays,
months and leap years are kept) and the prices scaled so the last close is 1000. Nothing after the close is sent
until the call is saved.

A call (side, draw, protected swing, confidence, evidence tags, note, "I recognise this chart", the time taken)
is kept in ``<root>/calls.jsonl`` (git-ignored) and scored at once on the real prices:
- **the week:** the next week closed beyond its open on the call's side, against the market's share of such weeks
  over the window (drift);
- **the race:** H-AE's (``search_narrative.race``): held when a D1 candle trades at the draw before one closes
  beyond the protected swing, a day doing both failing; against H-AE's matched control and a random walk's odds.

The reveal adds the market, the real dates, the next eight weeks of D1 and reader v0's state at that close
(``algo_mind.dis``). The totals leave out NONE calls and recognised charts.

A chart is named to the page only by its number in the order; the market and dates stay on the server.

    GET  /api/weekly/chart[?id=n]     POST /api/weekly/call     GET /api/weekly/reveal?id=n     GET /api/weekly/summary
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np
import pandas as pd

from algo_research.search_crt import _interval
from algo_research.search_narrative import ADR_N, control_share, race

__all__ = ["EVIDENCE", "SIDES", "WeeklyApp", "WINDOW"]

MARKETS = ("DXY", "XAUUSD", "EURUSD", "GBPUSD", "US100", "US500", "US30", "GER40", "UK100")
WINDOW = (pd.Timestamp("1996-01-01"), pd.Timestamp("2017-12-31"))
WARM_WEEKS = 52
YEARS = 56                      # two 28-year calendar cycles
LAST = 1000.0
SHOW = {"MN1": 180, "W1": 520, "D1": 750}            # the same depth for every market
AFTER_WEEKS = 8
TARGET_CALLS = 300
SEED = 20261102
SIDES = {"BULLISH": 1, "BEARISH": -1, "NONE": 0}
EVIDENCE = ("External high or low taken", "W1 turtle soup", "D1 turtle soup", "CISD or MSS", "Displacement",
            "Discount or premium of the range", "Draw: a gap (FVG)", "Draw: an old high or low",
            "Time: a month or quarter opening", "Trend continuation", "Consolidation, then expansion")
_DAY = 86_400 * 10**9


def _load(market: str) -> pd.DataFrame:
    from algo_research.search_state import load                    # noqa: PLC0415 (pyarrow only when served)
    return load(market)


class _Market:
    """One market's days, weeks (Monday to Friday) and months, the eligible weeks and what scoring needs."""

    def __init__(self, name: str, days: pd.DataFrame) -> None:
        d = days[["date", "open", "high", "low", "close"]].copy()
        d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.normalize()
        weekend = d["date"].dt.dayofweek >= 5
        d.loc[weekend, "date"] += pd.to_timedelta(7 - d.loc[weekend, "date"].dt.dayofweek, unit="D")
        g = d.sort_values("date", kind="stable").groupby("date", sort=True)
        self.d1 = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                                "close": g["close"].last()}).reset_index()
        self.name = name
        dates = self.d1["date"]
        self.d1["monday"] = dates - pd.to_timedelta(dates.dt.dayofweek, unit="D")
        self.d1["month"] = dates.dt.to_period("M").dt.to_timestamp()
        w = self.d1.groupby("monday", sort=True)
        self.w1 = pd.DataFrame({"open": w["open"].first(), "high": w["high"].max(), "low": w["low"].min(),
                                "close": w["close"].last(), "last": w["date"].last(),
                                "end": w["date"].apply(lambda x: x.index[-1])}).reset_index()
        self.hi, self.lo, self.cl = (self.d1[k].to_numpy(float) for k in ("high", "low", "close"))
        self.adr = pd.Series(self.hi - self.lo).rolling(ADR_N).mean().to_numpy()
        first = max(WINDOW[0], self.w1["monday"].iloc[min(WARM_WEEKS, len(self.w1) - 1)])
        ok = (self.w1["monday"] >= first) & (self.w1["last"] <= WINDOW[1])
        ok &= self.w1.index < len(self.w1) - 1                                      # a week after it exists
        self.eligible = self.w1.index[ok].to_numpy()
        nxt = self.w1.iloc[self.eligible + 1]
        self.drift = {1: float((nxt["close"] > nxt["open"]).mean()), -1: float((nxt["close"] < nxt["open"]).mean())}
        ends = self.w1["end"].to_numpy(int)[self.eligible]
        keep = (ends + 1 < len(self.d1)) & np.isfinite(self.adr[ends])
        self.c_starts, self.c_closes, self.c_adrs = ends[keep] + 1, self.cl[ends[keep]], self.adr[ends[keep]]
        self._timeline = None
        self._timeline_lock = threading.Lock()

    def week(self, monday: pd.Timestamp) -> int:
        rows = self.w1.index[self.w1["monday"] == monday]
        if not len(rows):
            raise KeyError(f"no week {monday:%Y-%m-%d} in {self.name}")
        return int(rows[0])

    def timeline(self):
        with self._timeline_lock:
            if self._timeline is None:
                from algo_mind.dis import daily_market, reader_turns, states    # noqa: PLC0415
                m = daily_market(self.d1[["date", "open", "high", "low", "close"]])
                self._timeline = states(reader_turns(m), m.hist["D1"])
            return self._timeline


def _shift(t: pd.Timestamp) -> str:
    return f"{t.year + YEARS:04d}-{t.month:02d}-{t.day:02d}"


def _bars(frame: pd.DataFrame, when: str, k: float) -> list[dict]:
    return [{"time": _shift(pd.Timestamp(r[when])), "open": round(r["open"] * k, 4), "high": round(r["high"] * k, 4),
             "low": round(r["low"] * k, 4), "close": round(r["close"] * k, 4)} for r in frame.to_dict("records")]


class WeeklyApp:
    """The blind weekly calls: the order, the charts, the calls and their scores, the totals."""

    def __init__(self, root: Path, loader: Callable[[str], pd.DataFrame] = _load, markets: Sequence[str] = MARKETS,
                 seed: int = SEED, reader: bool = True) -> None:
        self.root, self.loader, self.markets, self.seed, self.reader = Path(root), loader, tuple(markets), seed, reader
        self._markets: dict[str, _Market] = {}
        self._order: Optional[list[str]] = None
        self._lock = threading.RLock()
        self._warming = False

    # ── the charts ─────────────────────────────────────────────────────────

    def market(self, name: str) -> _Market:
        with self._lock:
            if name not in self._markets:
                self._markets[name] = _Market(name, self.loader(name))
            return self._markets[name]

    def order(self) -> list[str]:
        with self._lock:
            if self._order is None:
                ids = sorted(f"{m}:{self.market(m).w1['monday'].iloc[i]:%Y-%m-%d}"
                             for m in self.markets for i in self.market(m).eligible)
                rng = np.random.default_rng(self.seed)
                self._order = [ids[i] for i in rng.permutation(len(ids))]
                self._warm()
            return self._order

    def _warm(self) -> None:
        """Reader v0's timelines (about 6 s a market), built in the background so a reveal doesn't wait."""
        if self.reader and not self._warming:
            self._warming = True
            threading.Thread(target=lambda: [self.market(m).timeline() for m in self.markets], daemon=True).start()

    def key(self, chart_id) -> str:
        """The market and Monday behind a chart's number (its place in the order), which alone the page sees."""
        order = self.order()
        try:
            n = int(chart_id)
        except (TypeError, ValueError):
            raise ValueError("id: a chart number") from None
        if not 0 <= n < len(order):
            raise KeyError(f"no chart {n}")
        return order[n]

    def _item(self, item: str) -> tuple[_Market, int]:
        name, monday = item.split(":")
        m = self.market(name)
        return m, m.week(pd.Timestamp(monday))

    def chart(self, query: Optional[dict] = None) -> dict:
        """Chart number ``id`` (default: the first not yet called), blind."""
        done = self.records()
        order = self.order()
        given = (query or {}).get("id")
        n = int(given) if given not in (None, "") else next((i for i, x in enumerate(order) if x not in done), None)
        if n is None:
            return {"id": None, "done": len(done), "total": len(order)}
        item = self.key(n)
        m, w = self._item(item)
        end = int(m.w1["end"].iloc[w])
        k = LAST / float(m.cl[end])
        d1 = m.d1.iloc[: end + 1]
        w1 = m.w1.iloc[: w + 1]
        g = d1.groupby("month", sort=True)
        mn1 = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                            "close": g["close"].last()}).reset_index()
        frames = {"MN1": (mn1, "month"), "W1": (w1, "monday"), "D1": (d1, "date")}
        bars = {tf: _bars(f if SHOW[tf] is None else f.tail(SHOW[tf]), when, k) for tf, (f, when) in frames.items()}
        return {"id": n, "done": len(done), "total": len(order), "last": LAST, "bars": bars,
                "called": item in done, "evidence": list(EVIDENCE)}

    # ── the calls ──────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self.root / "calls.jsonl"

    def records(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        out = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["id"]] = rec
        return out

    def call(self, body: dict) -> dict:
        """Check, keep and score a call; the answer is the reveal."""
        n = body.get("id")
        item = self.key(n)
        side_name = str(body.get("side") or "")
        if side_name not in SIDES:
            raise ValueError("side: BULLISH, BEARISH or NONE")
        with self._lock:
            if item in self.records():
                raise ValueError(f"chart {n}: already called")
            m, w = self._item(item)
            end = int(m.w1["end"].iloc[w])
            k = LAST / float(m.cl[end])
            side = SIDES[side_name]
            evidence = [str(e) for e in body.get("evidence") or []]
            if any(e not in EVIDENCE for e in evidence):
                raise ValueError("evidence: tags from the list")
            confidence = int(body.get("confidence") or 0)
            draw = protected = None
            if side:
                draw, protected = float(body["draw"]), float(body["protected"])
                if not (side * (protected - LAST) < 0 < side * (draw - LAST)):
                    raise ValueError(f"a {side_name.lower()} call's protected swing is "
                                     f"{'below' if side > 0 else 'above'} the last close and its draw beyond it")
                if confidence not in (1, 2, 3):
                    raise ValueError("confidence: 1, 2 or 3")
            rec = {"id": item, "n": int(n), "market": m.name, "monday": f"{m.w1['monday'].iloc[w]:%Y-%m-%d}",
                   "friday": f"{m.d1['date'].iloc[end]:%Y-%m-%d}", "side": side_name, "draw": draw,
                   "protected": protected, "scale": k,
                   "draw_real": None if draw is None else draw / k,
                   "protected_real": None if protected is None else protected / k,
                   "confidence": confidence or None, "evidence": evidence, "note": str(body.get("note") or ""),
                   "recognised": bool(body.get("recognised")), "ms": int(body.get("ms") or 0),
                   "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            rec["score"] = self._score(m, w, side, rec["draw_real"], rec["protected_real"])
            rec["reader"] = self._reader(m, w, k) if self.reader else None
            self.root.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        return self.reveal({"id": n})

    def _score(self, m: _Market, w: int, side: int, draw: Optional[float], protected: Optional[float]) -> dict:
        nxt = m.w1.iloc[w + 1]
        move = float(nxt["close"] - nxt["open"])
        out = {"next_open": float(nxt["open"]), "next_close": float(nxt["close"]), "week_up": move > 0,
               "week_hit": None, "drift": None, "race": None, "days": None, "control": None, "n_control": 0,
               "geo": None}
        if not side:
            return out
        out.update(week_hit=float(side * move > 0), drift=m.drift[side])
        end = int(m.w1["end"].iloc[w])
        p, adr = float(m.cl[end]), float(m.adr[end])
        outcome, row = race(m.hi, m.lo, m.cl, end + 1, side, draw, protected)
        out["race"] = outcome
        if row >= 0:
            out["days"] = int((m.d1["date"].iloc[row] - m.d1["date"].iloc[end]).days)
        if np.isfinite(adr) and adr > 0:
            a, b = side * (draw - p) / adr, side * (p - protected) / adr
            share, n = control_share(m.hi, m.lo, m.cl, m.c_starts, m.c_closes, m.c_adrs, side, a, b)
            out.update(control=None if not n else share, n_control=n, geo=b / (a + b))
        return out

    def _reader(self, m: _Market, w: int, k: float) -> dict:
        """Reader v0's state at the Friday close, on the daily history (its prices scaled as the chart's)."""
        from algo_mind.dis import state_at                                     # noqa: PLC0415
        end = int(m.w1["end"].iloc[w])
        t = int(pd.Timestamp(m.d1["date"].iloc[end], tz="UTC").value) + _DAY
        s = state_at(m.timeline(), t, m.name)
        out = {"side": s.direction, "state": s.state}
        if s.side:
            out.update(draw=round(s.draw["ce"] * k, 4) if s.draw else None, protected=round(s.protected * k, 4),
                       since=pd.Timestamp(s.since, tz="UTC").strftime("%Y-%m-%d"),
                       evidence=[e for e, _ in s.evidence])
        return out

    def reveal(self, query: dict) -> dict:
        """A saved call with its market, real dates, the next eight weeks of D1 and its score."""
        item = self.key(query.get("id"))
        rec = self.records().get(item)
        if rec is None:
            raise LookupError(f"chart {query.get('id')}: not called yet (the reveal comes after the save)")
        m, w = self._item(item)
        end = int(m.w1["end"].iloc[w])
        after = m.d1.iloc[end + 1: end + 1 + 5 * AFTER_WEEKS]
        return {**rec, "bars_after": _bars(after, "date", rec["scale"])}

    # ── the totals ─────────────────────────────────────────────────────────

    def summary(self) -> dict:
        recs = list(self.records().values())
        sided = [r for r in recs if r["side"] != "NONE" and not r["recognised"]]
        t = pd.DataFrame([{"id": r["id"], "market": r["market"], "confidence": r["confidence"],
                           "hit": r["score"]["week_hit"], "drift": r["score"]["drift"],
                           "held": {"held": 1.0, "failed": 0.0}.get(r["score"]["race"]),
                           "control": r["score"]["control"],
                           "agree": None if not r.get("reader") or r["reader"]["side"] == "NONE"
                           else float(r["reader"]["side"] == r["side"])} for r in sided])

        def judge(g: pd.DataFrame, value: str, base: str) -> dict:
            g = g.dropna(subset=[value, base]) if len(g) else g
            if not len(g):
                return {"n": 0}
            x = (g[value] - g[base]).to_numpy(float)
            lo, hi = _interval(g["id"].to_numpy(), x, 0.95) if len(g) > 1 else (float("nan"), float("nan"))
            return {"n": int(len(g)), "hit": float(g[value].mean()), "base": float(g[base].mean()),
                    "excess": float(x.mean()), "lo": lo, "hi": hi}

        out = {"calls": len(recs), "sided": len(sided), "none": sum(r["side"] == "NONE" for r in recs),
               "recognised": sum(bool(r["recognised"]) for r in recs), "target": TARGET_CALLS,
               "remaining": len(self.order()) - len(recs), "bar": [0.57, 0.60]}
        if t.empty:
            return {**out, "week": {"n": 0}, "race": {"n": 0}, "by_confidence": {}, "by_market": {}, "agree": None}
        out["week"], out["race"] = judge(t, "hit", "drift"), judge(t, "held", "control")
        out["by_confidence"] = {int(c): {"week": judge(g, "hit", "drift"), "race": judge(g, "held", "control")}
                                for c, g in t.groupby("confidence")}
        out["by_market"] = {mk: {"week": judge(g, "hit", "drift"), "race": judge(g, "held", "control")}
                            for mk, g in t.groupby("market")}
        a = t.dropna(subset=["agree"])
        out["agree"] = {"n": int(len(a)), "share": float(a["agree"].mean())} if len(a) else None
        return _clean(out)


def _clean(x):
    """NaN as None, for JSON."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x
