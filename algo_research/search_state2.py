"""The 2018-2024 search: H-Z, the weekly state widened (docs/research/SEARCH_2018_2024.md).

H-Y's weekly state (``search_state``), with what the trader's context reads beyond one market's candles:
- **structure, for MN1, W1 and D1:** the latest break of a confirmed swing and the latest CISD (their side and age),
  the distance to the nearest unmitigated order block's mean threshold above and below (the CISD rule: a run of
  opposite closes, its bodies), and to the nearest inversion FVG (a filled gap, flipped);
- **anchors:** the week's open against the month's and the quarter's open;
- **regime:** the weekly range's percentile in its last two years, and the efficiency ratio on W1 and D1;
- **intermarket:** the dollar's own weekly state, and SMT and relative strength against a partner market;
- **macro and risk:** the 10-year yield's and the 10-year-minus-3-month curve's four-week change, the curve's level,
  and the VIX's one-year percentile and four-week change.

Fitted and judged as H-Y: the same model, the weeks before 2018-07, judged on 2018-07 to 2022.

    python -m algo_research.search_state2 --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_d1 import MARKETS, OUT
from algo_research.search_state import (CAP, FEATURES as V1, FIT_UNTIL, FRAMES, JUDGE, WARM_UP_WEEKS, YAHOO, _Frame,
                                        build_frames, judge, load, week_state)

__all__ = ["FEATURES", "MACRO", "PARTNER", "STRUCTURE", "macro_table", "state_table2", "widen"]

#: Each market's partner for SMT and relative strength, and whether they move apart (the dollar).
PARTNER = {"DXY": ("EURUSD", True), "XAUUSD": ("DXY", True), "EURUSD": ("GBPUSD", False),
           "GBPUSD": ("EURUSD", False), "US100": ("US500", False), "US500": ("US100", False),
           "US30": ("US500", False), "GER40": ("UK100", False), "UK100": ("GER40", False)}
MACRO_SYMBOLS = {"TNX": "^TNX", "IRX": "^IRX", "VIX": "^VIX"}
STRUCT_PER_FRAME = ("bos", "bos_age", "cisd", "cisd_age", "ob_up", "ob_dn", "ifvg_up", "ifvg_dn")
STRUCTURE = tuple(f"{tf}_{x}" for tf in FRAMES for x in STRUCT_PER_FRAME) + ("month_open", "quarter_open")
REGIME = ("w1_vol_pct", "w1_er", "d1_er")
INTERMARKET = ("dxy_w1_body", "dxy_w1_pos", "dxy_mn1_pd", "smt_w1", "smt_mn1", "rs_w1")
MACRO = ("y10_chg4w", "curve", "curve_chg4w", "vix_pct", "vix_chg4w")
FEATURES = V1 + STRUCTURE + REGIME + INTERMARKET + MACRO
AGE_CAP = 20


class _Frame2(_Frame):
    """H-Y's frame, with the breaks, CISDs, order blocks and inversion FVGs each candle leaves known."""

    def __init__(self, bars: pd.DataFrame, tf: str) -> None:
        super().__init__(bars, tf)
        n, o, c = len(self.c), self.o, self.c
        big = np.iinfo(np.int64).max
        # breaks: a close beyond the latest swing confirmed by then
        self.bos_side, self.bos_at = np.zeros(n), np.full(n, -1)
        sh_known = {i + 2: i for i in self.sh}
        sl_known = {i + 2: i for i in self.sl}
        hi_lvl = lo_lvl = None
        side, at = 0, -1
        for k in range(n):
            if hi_lvl is not None and c[k] > hi_lvl:
                side, at, hi_lvl = 1, k, None
            elif lo_lvl is not None and c[k] < lo_lvl:
                side, at, lo_lvl = -1, k, None
            if k in sh_known:
                hi_lvl = self.h[sh_known[k]]
            if k in sl_known:
                lo_lvl = self.l[sl_known[k]]
            self.bos_side[k], self.bos_at[k] = side, at
        # CISDs and the CISD rule's order blocks: a run of opposite closes, closed through at its first open
        self.cisd_side, self.cisd_at = np.zeros(n), np.full(n, -1)
        sign = np.sign(c - o)
        obs = []
        down = up = None                     # (first index, last index) of the latest unbroken run of each side
        side, at = 0, -1
        for k in range(n):
            if down is not None and c[k] > o[down[0]]:
                a, b = down
                body = np.r_[o[a:b + 1], c[a:b + 1]]
                obs.append((k, body.min(), body.max(), 1))
                side, at, down = 1, k, None
            elif up is not None and c[k] < o[up[0]]:
                a, b = up
                body = np.r_[o[a:b + 1], c[a:b + 1]]
                obs.append((k, body.min(), body.max(), -1))
                side, at, up = -1, k, None
            if sign[k] < 0:
                down = (k, k) if (down is None or down[1] != k - 1) else (down[0], k)
            elif sign[k] > 0:
                up = (k, k) if (up is None or up[1] != k - 1) else (up[0], k)
            self.cisd_side[k], self.cisd_at[k] = side, at
        rows = []
        for k, lo, hi, s in obs:             # mitigated by a close beyond the far edge
            beyond = np.nonzero(c[k + 1:] < lo)[0] if s > 0 else np.nonzero(c[k + 1:] > hi)[0]
            rows.append((k, lo, hi, s, k + 1 + beyond[0] if len(beyond) else big))
        ob = np.array(rows, float).reshape(-1, 5)
        self.ob_k, self.ob_lo, self.ob_hi, self.ob_side, self.ob_end = (ob[:, j] for j in range(5))
        # inversion FVGs: a gap closed through flips side, until a close beyond its other edge
        inv = []
        for lo, hi, s, f in zip(self.g_lo, self.g_hi, self.g_side, self.g_fill):
            if f >= big:
                continue
            f = int(f)
            beyond = np.nonzero(c[f + 1:] > hi)[0] if s > 0 else np.nonzero(c[f + 1:] < lo)[0]
            inv.append((f, lo, hi, -s, f + 1 + beyond[0] if len(beyond) else big))
        iv = np.array(inv, float).reshape(-1, 5)
        self.iv_k, self.iv_lo, self.iv_hi, self.iv_side, self.iv_end = (iv[:, j] for j in range(5))

    def read(self, k: int, price: float) -> dict:
        out = super().read(k, price)
        mr = self.mean[k]
        cap = lambda x: float(min(CAP, x / mr))                                    # noqa: E731
        age = lambda at: float(min(AGE_CAP, k - at) / AGE_CAP) if at >= 0 else 1.0   # noqa: E731
        live = (self.ob_k <= k) & (self.ob_end > k)
        mt = (self.ob_lo + self.ob_hi) / 2
        up, dn = live & (mt > price), live & (mt < price)
        ilive = (self.iv_k <= k) & (self.iv_end > k)
        iup, idn = ilive & (self.iv_lo > price), ilive & (self.iv_hi < price)
        out.update({"bos": float(self.bos_side[k]), "bos_age": age(self.bos_at[k]),
                    "cisd": float(self.cisd_side[k]), "cisd_age": age(self.cisd_at[k]),
                    "ob_up": cap(np.min(mt[up]) - price) if up.any() else CAP,
                    "ob_dn": cap(price - np.max(mt[dn])) if dn.any() else CAP,
                    "ifvg_up": cap(np.min(self.iv_lo[iup]) - price) if iup.any() else CAP,
                    "ifvg_dn": cap(price - np.max(self.iv_hi[idn])) if idn.any() else CAP})
        return out


def _er(close: np.ndarray, k: int, n: int) -> float:
    """Kaufman's efficiency ratio over the ``n`` closes to ``k``: net move over the path's length."""
    if k < n:
        return 0.5
    path = np.abs(np.diff(close[k - n:k + 1])).sum()
    return float(abs(close[k] - close[k - n]) / path) if path > 0 else 0.0


def _anchors_regime(row: dict, frames: dict, days: pd.DataFrame, first: pd.Timestamp, price: float) -> dict:
    """The week's open against its month's and quarter's open, and the regime, from candles closed before it."""
    before = days[days["date"] < first]
    mn = frames["MN1"]
    kw, kd, km = (frames[tf].closed_before(np.datetime64(first, "ns")) for tf in ("W1", "D1", "MN1"))
    mr = mn.mean[km]
    month = before[before["date"].dt.to_period("M") == first.to_period("M")]
    quarter = before[before["date"].dt.to_period("Q") == first.to_period("Q")]
    w1 = frames["W1"]
    hist = w1.mean[max(0, kw - 104):kw + 1]
    hist = hist[np.isfinite(hist)]
    return {**row,
            "month_open": float((price - month["open"].iat[0]) / mr) if len(month) else 0.0,
            "quarter_open": float((price - quarter["open"].iat[0]) / mr) if len(quarter) else 0.0,
            "w1_vol_pct": float((hist <= w1.mean[kw]).mean()) if len(hist) else 0.5,
            "w1_er": _er(w1.c, kw, 13), "d1_er": _er(frames["D1"].c, kd, 20)}


def state_table2(market: str, days: pd.DataFrame) -> pd.DataFrame:
    """Every week's own widened state (H-Y's, structure, anchors and regime) and its outcome."""
    fr = build_frames(days)
    frames = {tf: _Frame2(fr[tf], tf) for tf in FRAMES}
    weeks = fr["W1"]
    rows = []
    for w in range(WARM_UP_WEEKS, len(weeks)):
        first = pd.Timestamp(weeks["first"].iat[w])
        row = week_state(market, frames, first, float(weeks["open"].iat[w]), float(weeks["close"].iat[w - 1]),
                         pd.Timestamp(weeks["last"].iat[w - 1]), pd.Timestamp(weeks["last"].iat[w]))
        if row is None:
            continue
        row = _anchors_regime(row, frames, days, first, float(weeks["open"].iat[w]))
        took_hi = float(weeks["high"].iat[w - 1] > weeks["high"].iat[w - 2]) if w >= 2 else 0.0
        took_lo = float(weeks["low"].iat[w - 1] < weeks["low"].iat[w - 2]) if w >= 2 else 0.0
        km = frames["MN1"].closed_before(np.datetime64(first, "ns"))
        m = frames["MN1"]
        rows.append({**row, "close": float(weeks["close"].iat[w]), "took_hi": took_hi, "took_lo": took_lo,
                     "mn_took_hi": float(m.h[km] > m.h[km - 1]), "mn_took_lo": float(m.l[km] < m.l[km - 1]),
                     "w1_ret": float((weeks["close"].iat[w - 1] - weeks["close"].iat[w - 2]) / frames["W1"].mean[
                         frames["W1"].closed_before(np.datetime64(first, "ns"))]) if w >= 2 else 0.0})
    t = pd.DataFrame(rows)
    return t.assign(up=np.sign(t["close"] - t["open"]))


def _smt(mine_hi, mine_lo, other_hi, other_lo, apart: bool) -> np.ndarray:
    """+1 bullish SMT (a low taken that the partner didn't confirm), -1 bearish (a high), 0 none; for markets moving
    apart, the partner's confirmation of a high is its low."""
    if apart:
        other_hi, other_lo = other_lo, other_hi
    bull = (mine_lo == 1) & (other_lo == 0)
    bear = (mine_hi == 1) & (other_hi == 0)
    return np.where(bull & ~bear, 1.0, np.where(bear & ~bull, -1.0, 0.0))


def macro_table(root=YAHOO) -> pd.DataFrame:
    """Each week's macro and risk state at its open, from the daily closes before it (Monday-keyed)."""
    closes = {}
    for name in MACRO_SYMBOLS:
        d = pd.read_parquet(root / f"{name}_D1.parquet")[["date", "close"]].dropna()
        closes[name] = d.set_index("date")["close"]
    daily = pd.DataFrame(closes).sort_index().ffill()
    daily["curve"] = daily["TNX"] - daily["IRX"]
    weekly = daily.groupby(daily.index - pd.to_timedelta(daily.index.dayofweek, unit="D")).last()
    vix_pct = daily["VIX"].rolling(252, min_periods=120).apply(lambda s: (s <= s.iloc[-1]).mean(), raw=False)
    weekly["vix_pct"] = vix_pct.groupby(daily.index - pd.to_timedelta(daily.index.dayofweek, unit="D")).last()
    out = pd.DataFrame({"y10_chg4w": weekly["TNX"].diff(4), "curve": weekly["curve"],
                        "curve_chg4w": weekly["curve"].diff(4), "vix_pct": weekly["vix_pct"],
                        "vix_chg4w": np.log(weekly["VIX"]).diff(4)})
    out.index = out.index + pd.Timedelta(days=7)           # the week before's closes, read at this week's open
    return out.rename_axis("week").reset_index()


def widen(tables: dict[str, pd.DataFrame], macro: pd.DataFrame) -> pd.DataFrame:
    """The markets' own widened states joined with the dollar's, their partner's and the macro state, by week."""
    need = ["week", "took_hi", "took_lo", "mn_took_hi", "mn_took_lo", "w1_ret", "W1_body", "W1_pos", "MN1_pd"]
    blank = pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c == "week" else float) for c in need})
    tables = {m: t for m, t in tables.items() if len(t)}
    get = lambda m: tables.get(m, blank)                                    # noqa: E731  (a market missing live)
    dxy = get("DXY")[["week", "W1_body", "W1_pos", "MN1_pd"]].rename(
        columns={"W1_body": "dxy_w1_body", "W1_pos": "dxy_w1_pos", "MN1_pd": "dxy_mn1_pd"})
    parts = []
    for market, t in tables.items():
        partner, apart = PARTNER[market]
        p = get(partner)[["week", "took_hi", "took_lo", "mn_took_hi", "mn_took_lo", "w1_ret"]].add_prefix("p_")
        x = t.merge(dxy, on="week", how="left").merge(p, left_on="week", right_on="p_week", how="left")
        x["smt_w1"] = _smt(x["took_hi"], x["took_lo"], x["p_took_hi"].fillna(-1), x["p_took_lo"].fillna(-1), apart)
        x["smt_mn1"] = _smt(x["mn_took_hi"], x["mn_took_lo"], x["p_mn_took_hi"].fillna(-1),
                            x["p_mn_took_lo"].fillna(-1), apart)
        x["rs_w1"] = x["w1_ret"] - np.where(apart, -1, 1) * x["p_w1_ret"].fillna(0)
        parts.append(x)
    t = pd.concat(parts, ignore_index=True).merge(macro, on="week", how="left")
    fill = {c: 0.0 for c in INTERMARKET + MACRO}
    return t.fillna(fill)


def main() -> None:
    from algo_research.search_state import _line, fit_and_call
    from sklearn.inspection import permutation_importance

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    parser.parse_args()
    tables = {}
    for market in MARKETS:
        tables[market] = state_table2(market, load(market))
        print(f"{market}: {len(tables[market]):,} weeks", flush=True)
    t = widen(tables, macro_table())
    fit = t[t["week"] < FIT_UNTIL]
    judged = t[(t["week"] >= JUDGE[0]) & (t["week"] < JUDGE[1])]
    OUT.mkdir(parents=True, exist_ok=True)
    head = ["| Model | Calls | Hit | Drift | Excess (pts) | 95% weeks | Markets > 0 | Passes (H-Y's rule) |",
            "|---|---|---|---|---|---|---|---|"]
    lines = [f"Fitted on {len(fit[fit['up'] != 0]):,} weeks before {FIT_UNTIL.date()}; judged on "
             f"{len(judged[judged['up'] != 0]):,} weeks {JUDGE[0].date()} to 2022.", "", *head]
    groups = {"v2 (all)": FEATURES, "v1 inputs on these weeks": V1,
              "v2 without structure": tuple(f for f in FEATURES if f not in STRUCTURE),
              "v2 without regime": tuple(f for f in FEATURES if f not in REGIME),
              "v2 without intermarket": tuple(f for f in FEATURES if f not in INTERMARKET),
              "v2 without macro": tuple(f for f in FEATURES if f not in MACRO)}
    results, model_v2, called_v2 = {}, None, None
    for name, feats in groups.items():
        f_, c_, m_ = fit_and_call(fit, judged, "gbm", feats)
        r = results[name] = judge(c_)
        lines.append(_line(name if name != "v2 (all)" else "**H-Z: v2's top and bottom thirds**", r))
        if name == "v2 (all)":
            model_v2, called_v2 = m_, c_
            lines.append(_line("v2 in sample", judge(f_)))
    called_v2.to_parquet(OUT / "state2_develop.parquet")
    r = results["v2 (all)"]
    diff = r["excess"] - results["v1 inputs on these weeks"]["excess"]
    lines += ["", f"v2 − v1 on the same weeks: {100 * diff:+.1f} pts",
              "Excess per market, v2: " + ", ".join(f"{m} {100 * v:+.1f} ({n})" for m, (v, n) in r["per_market"].items())]
    moved = called_v2[called_v2["up"] != 0]
    imp = permutation_importance(model_v2, moved[list(FEATURES)].to_numpy(float), (moved["up"] > 0).astype(int),
                                 scoring="roc_auc", n_repeats=5, random_state=0)
    order = np.argsort(-imp.importances_mean)[:15]
    lines += ["", "Permutation importance on the judged weeks (ROC AUC lost):",
              ", ".join(f"{FEATURES[i]} {imp.importances_mean[i]:+.4f}" for i in order)]
    print("\n".join(lines))


if __name__ == "__main__":
    main()


def own_state2_at(market: str, days: pd.DataFrame, monday: pd.Timestamp, price=None):
    """A market's own widened state at the open of the week of ``monday``, read only from days before it (Algo
    Mind's live senses; as ``algo_mind.sources.state_at``): H-Y's state, structure, anchors, regime and what the
    partner join needs. Without ``price``: the week's open once it has opened, else the last close. None while a
    frame lacks history; and whether the state is provisional (its Friday missing)."""
    from datetime import timedelta

    monday = pd.Timestamp(monday).normalize()
    opened = days[(days["date"] >= monday) & (days["date"] < monday + timedelta(days=7))]
    before = days[days["date"] < monday].reset_index(drop=True)
    if before.empty:
        return None, True
    if price is None:
        price = float(opened["open"].iat[0]) if len(opened) else float(before["close"].iat[-1])
    fr = build_frames(before)
    fr["MN1"] = fr["MN1"][fr["MN1"]["first"].dt.to_period("M") != monday.to_period("M")].reset_index(drop=True)
    frames = {tf: _Frame2(fr[tf], tf) for tf in FRAMES}
    weeks = fr["W1"]
    row = week_state(market, frames, monday, float(price), float(weeks["close"].iat[-1]),
                     pd.Timestamp(weeks["last"].iat[-1]), monday + timedelta(days=4))
    provisional = bool(pd.Timestamp(before["date"].iat[-1]) < monday - timedelta(days=3))
    if row is None or len(weeks) < 2:
        return None, provisional
    row = _anchors_regime(row, frames, before, monday, float(price))
    m, w1 = frames["MN1"], frames["W1"]
    km, kw = m.closed_before(np.datetime64(monday, "ns")), w1.closed_before(np.datetime64(monday, "ns"))
    row.update({"took_hi": float(weeks["high"].iat[-1] > weeks["high"].iat[-2]),
                "took_lo": float(weeks["low"].iat[-1] < weeks["low"].iat[-2]),
                "mn_took_hi": float(m.h[km] > m.h[km - 1]), "mn_took_lo": float(m.l[km] < m.l[km - 1]),
                "w1_ret": float((weeks["close"].iat[-1] - weeks["close"].iat[-2]) / w1.mean[kw])})
    return row, provisional
