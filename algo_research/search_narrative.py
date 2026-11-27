"""H-AE: the trader's narrative held as the side (docs/research/SEARCH_2018_2024.md; context-engine Requirement 35).

Reader v0's narrative (``algo_research.sequence``, frozen at fe84645) through the directional state's machine
(``algo_mind.dis``) on Yahoo's daily history for the nine markets. Scored from 1996 (and a market's 53rd week) to
2022:

- **cell 1, the narrative:** each turn that sets the side, raced from its W1 close: held when a D1 candle trades
  at the draw's CE before one closes beyond the protected swing (a day doing both fails), against the same race
  from every W1 close of the market with the call's distances in 20-day average ranges (the control);
- **cell 2, the weekly side:** each week opened under a live side, closed on it, against the market's share of
  such weeks (drift).

Pass, per cell: excess above zero, its interval over resampled months at 97.5% above zero, 6 of 9 markets.

    python -m algo_research.search_narrative --window develop
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from typing import Optional
from unittest import mock

import numpy as np
import pandas as pd

from algo_mind.dis import daily_market, reader_turns, state_at, states
from algo_research import sequence as seq
from algo_research.search_crt import _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT
from algo_research.search_state import load

__all__ = ["VARIANTS", "control_share", "judge", "market_tables", "race", "run"]

WINDOW = (pd.Timestamp("1996-01-01"), pd.Timestamp("2023-01-01"))
WARM_WEEKS = 52
ADR_N = 20
LEVEL = 0.975                   # Holm for two cells
FOLDS = (("1996-99", "1996-01-01"), ("2000-04", "2000-01-01"), ("2005-09", "2005-01-01"),
         ("2010-14", "2010-01-01"), ("2015-18H1", "2015-01-01"), ("2018H2-22", "2018-07-01"))
_DAY = 86_400 * 10**9
_NEVER = np.iinfo(np.int64).max


# ── the race and its control ───────────────────────────────────────────────

def race(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, start: int, side: int, draw: float,
         protected: float) -> tuple[str, int]:
    """From row ``start``: held when a high (a low for a sell) reaches ``draw`` before a close beyond
    ``protected``; failed when the close comes first or on the same row; open when the path ends first."""
    n, a, w = len(hi), start, 256
    while a < n:
        b = min(n, a + w)
        hit = hi[a:b] >= draw if side > 0 else lo[a:b] <= draw
        out = cl[a:b] < protected if side > 0 else cl[a:b] > protected
        if hit.any() or out.any():
            i_hit = a + int(np.argmax(hit)) if hit.any() else _NEVER
            i_out = a + int(np.argmax(out)) if out.any() else _NEVER
            return ("held", i_hit) if i_hit < i_out else ("failed", i_out)
        a, w = b, 2 * w
    return "open", -1


def control_share(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, starts: np.ndarray, closes: np.ndarray,
                  adrs: np.ndarray, side: int, a: float, b: float) -> tuple[float, int]:
    """The held share of the race from each start (its first row, the close before it and the average range
    then), the draw ``a`` and the protected swing ``b`` average ranges from the close; over the races that resolve."""
    held = failed = 0
    for st, p, adr in zip(starts, closes, adrs):
        outcome, _ = race(hi, lo, cl, int(st), side, p + side * a * adr, p - side * b * adr)
        held += outcome == "held"
        failed += outcome == "failed"
    n = held + failed
    return (held / n if n else float("nan")), n


# ── the variants (the trader's open questions, Requirement 35.6) ───────────

def _w1_swing_lows(d1: pd.DataFrame, before: int) -> list[tuple[str, float]]:
    """External liquidity as any untaken W1 three-candle swing low closed before ``before``."""
    b = d1[d1["t_close"] <= before]
    if len(b) < 15:
        return []
    monday = (b["date"] - pd.to_timedelta(b["date"].dt.dayofweek, unit="D")).to_numpy()
    g = b.groupby(monday, sort=True)
    weeks = pd.DataFrame({"low": g["low"].min(), "t_close": g["t_close"].last()})
    lo, tc = weeks["low"].to_numpy(float), weeks["t_close"].to_numpy(np.int64)
    d_lo, d_tc = b["low"].to_numpy(float), b["t_close"].to_numpy(np.int64)
    out = []
    for i in range(1, len(weeks) - 1):
        if lo[i] < lo[i - 1] and lo[i] < lo[i + 1] and not (d_lo[d_tc > tc[i]] < lo[i]).any():
            out.append((f"week {pd.Timestamp(weeks.index[i]):%d %b %Y} low", float(lo[i])))
    return out


VARIANTS = {
    "as registered": {},
    "external = any untaken W1 swing": {"_external_lows": _w1_swing_lows},
    "no month window": {"W1_C2_WEEKS": 6},
}


@contextlib.contextmanager
def _variant(name: str):
    """Reader v0 with one default changed, for a companion; the frozen module itself is never edited."""
    with contextlib.ExitStack() as stack:
        for attr, value in VARIANTS[name].items():
            stack.enter_context(mock.patch.object(seq, attr, value))
        yield


# ── one market ─────────────────────────────────────────────────────────────

def market_tables(market: str, days: Optional[pd.DataFrame] = None,
                  variant: str = "as registered") -> dict[str, pd.DataFrame]:
    """The market's calls (cell 1), the turns it ignored, its weeks (cell 2) and its spans."""
    days = load(market) if days is None else days
    m = daily_market(days)
    d1, w1 = m.hist["D1"], m.hist["W1"]
    with _variant(variant):
        timeline = states(reader_turns(m), d1)
    hi, lo, cl = (d1[k].to_numpy(float) for k in ("high", "low", "close"))
    t_open, t_close = d1["t_open"].to_numpy(np.int64), d1["t_close"].to_numpy(np.int64)
    adr_rows = pd.Series(hi - lo).rolling(ADR_N).mean().to_numpy()
    first = max(WINDOW[0], pd.Timestamp(w1["monday"].iloc[min(WARM_WEEKS, len(w1) - 1)]))
    t0, t1 = int(pd.Timestamp(first, tz="UTC").value), int(pd.Timestamp(WINDOW[1], tz="UTC").value)

    def adr_at(t: int) -> float:
        k = int(np.searchsorted(t_close, t, side="right")) - 1
        return float(adr_rows[k]) if k >= 0 else float("nan")

    w_tc = w1["t_close"].to_numpy(np.int64)
    in_window = (w1["t_open"].to_numpy(np.int64) >= t0) & (w_tc <= t1)
    c_starts = np.searchsorted(t_open, w_tc[in_window], side="left")
    c_closes = w1["close"].to_numpy(float)[in_window]
    c_adrs = np.array([adr_at(int(t)) for t in w_tc[in_window]])
    ok = (c_starts < len(d1)) & np.isfinite(c_adrs)
    c_starts, c_closes, c_adrs = c_starts[ok], c_closes[ok], c_adrs[ok]
    close_at = dict(zip(w_tc.tolist(), w1["close"].to_numpy(float).tolist()))

    def score(turn: dict, kind: str, span=None) -> dict:
        s, t = turn["side"], turn["t"]
        row = {"market": market, "kind": kind, "side": s, "t": pd.Timestamp(t, tz="UTC").tz_localize(None),
               "outcome": "no draw", "held": np.nan, "control": np.nan, "n_control": 0, "geo": np.nan,
               "a": np.nan, "b": np.nan, "ended": span.reason if span else "",
               "live_days": (span.end - span.start) / _DAY if span and span.end != _NEVER else np.nan}
        p, adr = close_at.get(t, np.nan), adr_at(t)
        if turn["draw"] is None or not np.isfinite(p) or not np.isfinite(adr):
            return row
        ce, prot = turn["draw"]["ce"], turn["low"]
        a, b = s * (ce - p) / adr, s * (p - prot) / adr
        outcome, _ = race(hi, lo, cl, int(np.searchsorted(t_open, t, side="left")), s, ce, prot)
        share, n = control_share(hi, lo, cl, c_starts, c_closes, c_adrs, s, a, b)
        row.update(outcome=outcome, held={"held": 1.0, "failed": 0.0}.get(outcome, np.nan), control=share,
                   n_control=n, geo=b / (a + b), a=a, b=b)
        return row

    calls, ignored = [], []
    for span in timeline:
        if t0 <= span.start < t1:
            calls.append(score(span.turn, "call", span))
        ignored += [score(x, "ignored") for x in span.ignored if t0 <= x["t"] < t1]
    weeks = []
    for r in w1[in_window].itertuples():
        state = state_at(timeline, int(r.t_open), market)
        weeks.append({"market": market, "t": pd.Timestamp(r.monday), "side": state.side,
                      "up": float(r.close > r.open), "down": float(r.close < r.open)})
    weeks = pd.DataFrame(weeks)
    if not weeks.empty:
        weeks["expected"] = np.where(weeks["side"] > 0, weeks["up"].mean(),
                                     np.where(weeks["side"] < 0, weeks["down"].mean(), np.nan))
        weeks["hit"] = np.where(weeks["side"] > 0, weeks["up"], np.where(weeks["side"] < 0, weeks["down"], np.nan))
    return {"calls": pd.DataFrame(calls), "ignored": pd.DataFrame(ignored), "weeks": weeks,
            "spans": pd.DataFrame([{"market": market, "side": s.turn["side"], "start": s.start, "reason": s.reason}
                                   for s in timeline])}


def run(markets=MARKETS, variant: str = "as registered") -> dict[str, pd.DataFrame]:
    parts = [market_tables(m, variant=variant) for m in markets]
    return {k: pd.concat([p[k] for p in parts if not p[k].empty], ignore_index=True) for k in parts[0]}


# ── the judgement ──────────────────────────────────────────────────────────

def judge(t: pd.DataFrame, value: str, base: str) -> dict:
    """Excess of ``value`` over ``base`` in the rows where both are known: its mean, interval over calendar months
    (97.5%), the markets above zero and the pass."""
    g = t.dropna(subset=[value, base])
    if g.empty:
        return {"n": 0}
    excess = (g[value] - g[base]).to_numpy(float)
    lo, hi = _interval(g["t"].dt.to_period("M").astype(str).to_numpy(), excess, LEVEL)
    per = {m: (float((x[value] - x[base]).mean()), len(x)) for m, x in g.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    mean = float(excess.mean())
    return {"n": len(g), "value": float(g[value].mean()), "base": float(g[base].mean()), "excess": mean, "lo": lo,
            "hi": hi, "per_market": per, "positive": positive,
            "passes": bool(mean > 0 and lo > 0 and positive >= MIN_MARKETS)}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def _row(name: str, r: dict) -> str:
    if not r.get("n"):
        return f"| {name} | 0 | | | | | | |"
    return (f"| {name} | {r['n']:,} | {r['value']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
            f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/{len(r['per_market'])} | "
            f"{'yes' if r.get('passes') else 'no'} |")


def render(tables: dict[str, pd.DataFrame], extra: dict[str, dict[str, pd.DataFrame]]) -> str:
    calls, weeks, ignored, spans = tables["calls"], tables["weeks"], tables["ignored"], tables["spans"]
    live = weeks[weeks["side"] != 0]
    c1, c2 = judge(calls, "held", "control"), judge(live, "hit", "expected")
    head = "| Cell | n | Held / hit | Control / drift | Excess (pts) | 97.5% months | Markets > 0 | Passes |"
    out = [head, "|---|---|---|---|---|---|---|---|", _row("**1: the narrative's draw first**", c1),
           _row("**2: weeks under a live side**", c2), ""]
    out.append(f"H-AE {'PASSES' if c1.get('passes') or c2.get('passes') else 'fails'}.")
    out += ["", "Companions (not judged):", ""]
    ends = calls["ended"].value_counts().to_dict()
    out.append(f"- calls {len(calls)}: " + ", ".join(f"{k} {v}" for k, v in ends.items())
               + f"; races {calls['outcome'].value_counts().to_dict()}")
    out.append(f"- coverage: {len(live) / max(len(weeks), 1):.1%} of {len(weeks):,} market-weeks under a live side; "
               f"median days live {calls['live_days'].median():.0f}")
    if c2.get("n"):
        out.append(f"- cell 2's hit {c2['value']:.1%} against the 57-60% the costs need")
    g = calls.dropna(subset=["held", "control"])
    out.append(f"- geometry (touch against touch) {g['geo'].mean():.1%} beside the control {g['control'].mean():.1%}"
               f" and held {g['held'].mean():.1%}")
    rows = [head, "|---|---|---|---|---|---|---|---|"]
    for s, name in ((1, "buys"), (-1, "sells")):
        rows += [_row(f"cell 1, {name}", judge(calls[calls["side"] == s], "held", "control")),
                 _row(f"cell 2, {name}", judge(live[live["side"] == s], "hit", "expected"))]
    edges = [pd.Timestamp(x) for _, x in FOLDS] + [WINDOW[1]]
    for (name, _), a, b in zip(FOLDS, edges[:-1], edges[1:]):
        rows += [_row(f"cell 1, {name}", judge(calls[(calls["t"] >= a) & (calls["t"] < b)], "held", "control")),
                 _row(f"cell 2, {name}", judge(live[(live["t"] >= a) & (live["t"] < b)], "hit", "expected"))]
    if not ignored.empty:
        rows.append(_row("ignored turns (manipulation), own race", judge(ignored, "held", "control")))
    for name, t in extra.items():
        lv = t["weeks"][t["weeks"]["side"] != 0]
        rows += [_row(f"cell 1, {name}", judge(t["calls"], "held", "control")),
                 _row(f"cell 2, {name}", judge(lv, "hit", "expected"))]
    out += rows
    out += ["", "Per market, cell 1 / cell 2 (excess pts, n):"]
    for m in MARKETS:
        a, b = c1.get("per_market", {}).get(m), c2.get("per_market", {}).get(m)
        fa = f"{_pts(a[0])} ({a[1]})" if a else "–"
        fb = f"{_pts(b[0])} ({b[1]})" if b else "–"
        out.append(f"- {m}: {fa} / {fb}")
    return "\n".join(out)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="H-AE: the trader's narrative held as the side.")
    parser.add_argument("--window", choices=["develop"], default="develop")
    parser.add_argument("--markets", nargs="*", default=list(MARKETS))
    parser.add_argument("--no-companions", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    tables = run(args.markets)
    extra = {} if args.no_companions else {v: run(args.markets, v) for v in VARIANTS if v != "as registered"}
    OUT.mkdir(parents=True, exist_ok=True)
    for k, t in tables.items():
        t.to_parquet(OUT / f"narrative_{k}_develop.parquet")
    print(render(tables, extra))


if __name__ == "__main__":
    main()
