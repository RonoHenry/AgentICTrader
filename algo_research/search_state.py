"""The 2018-2024 search: H-Y, the learned combination of time and price at the weekly open
(docs/research/SEARCH_2018_2024.md).

At each week's open, the state of time (the quarter, the month and week, the opening gap) and of price on MN1, W1
and D1 (the last closed candle's shape and size, the two-candle read, consecutive closes, premium or discount,
liquidity and inefficiencies), read from Yahoo's long daily history (``scripts/export_yahoo_history.py``). A fixed
gradient-boosted model is fitted on the weeks before 2018-07 and judged on the weeks of 2018-07 to 2022, calling a
side only in its training probabilities' top and bottom thirds, against each market's drift.

    python -m algo_research.search_state --window develop
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from algo_research.search_crt import _interval
from algo_research.search_d1 import MARKETS, MIN_MARKETS, OUT
from algo_research.search_soup import _next_above
from algo_research.snapshot import SNAPSHOTS_DIR

__all__ = ["FEATURES", "build_frames", "load", "state_table", "fit_and_call", "judge"]

YAHOO = SNAPSHOTS_DIR / "yahoo-daily-to-2022"
FX = ("EURUSD", "GBPUSD")
#: Each market from where its bars have real highs and lows (the flat years cut, 2026-10-29).
START = {"DXY": "1990-01-01", "GER40": "1995-01-01", "XAUUSD": "2010-01-01"}
FIT_UNTIL, JUDGE = pd.Timestamp("2018-07-01"), (pd.Timestamp("2018-07-02"), pd.Timestamp("2023-01-01"))
WARM_UP_WEEKS = 52
MEAN_N = {"MN1": 12, "W1": 13, "D1": 20}
RANGE_N = {"MN1": 12, "W1": 26, "D1": 20}
CAP = 10.0
FRAMES = ("MN1", "W1", "D1")
PER_FRAME = ("pos", "wick", "body", "size", "expansion", "turtle", "streak", "pd", "swing_up", "swing_dn",
             "prev_up", "prev_dn", "fvg_up", "fvg_dn", "fvg_in")
TIME = ("quarter", "month_of_quarter", "week_of_month", "new_month", "new_quarter", "gap")
FEATURES = TIME + tuple(f"{f}_{x}" for f in FRAMES for x in PER_FRAME)
MODEL = dict(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=100, l2_regularization=1.0,
             random_state=0)


# ── the data ───────────────────────────────────────────────────────────────

def load(market: str, root=YAHOO) -> pd.DataFrame:
    """A market's daily bars, cleaned: an FX day's close is the next day's open (Yahoo's FX close is the day's open;
    FX trades round the clock), with the high and low widened to hold it; the flat early years cut; days with
    high = low dropped."""
    d = pd.read_parquet(root / f"{market}_D1.parquet")[["date", "open", "high", "low", "close"]]
    if market in FX:
        d = d.assign(close=d["open"].shift(-1)).dropna(subset=["close"])
        d = d.assign(high=d[["high", "open", "close"]].max(axis=1), low=d[["low", "open", "close"]].min(axis=1))
    d = d[(d["date"] >= START.get(market, "1900-01-01")) & (d["high"] > d["low"])]
    return d.sort_values("date").reset_index(drop=True)


def build_frames(days: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The days, their weeks (Monday to Friday by date) and their calendar months: open, high, low, close, the first
    and last date."""
    def group(key) -> pd.DataFrame:
        g = days.groupby(key, sort=True)
        return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                             "close": g["close"].last(), "first": g["date"].first(),
                             "last": g["date"].last()}).reset_index(drop=True)
    week = (days["date"] - pd.to_timedelta(days["date"].dt.dayofweek, unit="D")).to_numpy()
    month = days["date"].dt.to_period("M").to_numpy()
    d1 = days.assign(first=days["date"], last=days["date"])[["open", "high", "low", "close", "first", "last"]]
    return {"D1": d1.reset_index(drop=True), "W1": group(week), "MN1": group(month)}


# ── the state ──────────────────────────────────────────────────────────────

class _Frame:
    """One frame's arrays and what each candle leaves known at its close: swings and unfilled gaps."""

    def __init__(self, bars: pd.DataFrame, tf: str) -> None:
        self.tf = tf
        self.o, self.h, self.l, self.c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.last = bars["last"].to_numpy("datetime64[ns]")
        n = len(self.h)
        rng = self.h - self.l
        self.mean = pd.Series(rng).rolling(MEAN_N[tf], min_periods=MEAN_N[tf]).mean().to_numpy()
        self.top = pd.Series(self.h).rolling(RANGE_N[tf], min_periods=RANGE_N[tf]).max().to_numpy()
        self.bottom = pd.Series(self.l).rolling(RANGE_N[tf], min_periods=RANGE_N[tf]).min().to_numpy()
        sign = np.sign(self.c - self.o)
        streak = np.zeros(n)
        for i in range(n):
            streak[i] = sign[i] * (min(abs(streak[i - 1]) + 1, 5) if i and sign[i] == sign[i - 1] and sign[i] else 1)
        self.streak = streak
        mid = np.arange(2, n - 2)
        hi_ok = np.zeros(n, bool)
        lo_ok = np.zeros(n, bool)
        hi_ok[mid] = (self.h[mid] > self.h[mid - 1]) & (self.h[mid] > self.h[mid - 2]) & \
                     (self.h[mid] > self.h[mid + 1]) & (self.h[mid] > self.h[mid + 2])
        lo_ok[mid] = (self.l[mid] < self.l[mid - 1]) & (self.l[mid] < self.l[mid - 2]) & \
                     (self.l[mid] < self.l[mid + 1]) & (self.l[mid] < self.l[mid + 2])
        big = np.iinfo(np.int64).max
        self.sh = np.nonzero(hi_ok)[0]
        self.sh_taken = np.where((t := _next_above(self.h)[self.sh]) >= 0, t, big)
        self.sl = np.nonzero(lo_ok)[0]
        self.sl_taken = np.where((t := _next_above(-self.l)[self.sl]) >= 0, t, big)
        gaps = []
        for i in range(2, n):
            if self.l[i] > self.h[i - 2]:                      # bullish: filled by a close below its far edge
                beyond = np.nonzero(self.c[i + 1:] < self.h[i - 2])[0]
                gaps.append((i, self.h[i - 2], self.l[i], 1, i + 1 + beyond[0] if len(beyond) else big))
            if self.h[i] < self.l[i - 2]:                      # bearish: filled by a close above its far edge
                beyond = np.nonzero(self.c[i + 1:] > self.l[i - 2])[0]
                gaps.append((i, self.h[i], self.l[i - 2], -1, i + 1 + beyond[0] if len(beyond) else big))
        g = np.array(gaps, float).reshape(-1, 5)
        self.g_i, self.g_lo, self.g_hi, self.g_side, self.g_fill = g[:, 0], g[:, 1], g[:, 2], g[:, 3], g[:, 4]

    def closed_before(self, day: np.datetime64) -> int:
        """The last candle whose last date is before ``day`` (-1: none)."""
        return int(np.searchsorted(self.last, day, side="left")) - 1

    def read(self, k: int, price: float) -> dict:
        """The frame's state at ``price`` after candle ``k`` closed."""
        o, h, l, c, mr = self.o[k], self.h[k], self.l[k], self.c[k], self.mean[k]
        rng = h - l
        h1, l1 = self.h[k - 1], self.l[k - 1]
        expansion = 1 if c > h1 else -1 if c < l1 else 0
        turtle = 0 if expansion else (1 if l < l1 and h <= h1 else -1 if h > h1 and l >= l1 else 0)
        span = self.top[k] - self.bottom[k]
        up = (self.sh <= k - 2) & (self.sh_taken > k) & (self.h[self.sh] > price)
        dn = (self.sl <= k - 2) & (self.sl_taken > k) & (self.l[self.sl] < price)
        live = (self.g_i <= k) & (self.g_fill > k)
        above, below = live & (self.g_lo > price), live & (self.g_hi < price)
        inside = live & (self.g_lo <= price) & (self.g_hi >= price)
        cap = lambda x: float(min(CAP, x / mr)) if np.isfinite(x) else CAP      # noqa: E731
        return {"pos": (c - l) / rng, "wick": ((min(o, c) - l) - (h - max(o, c))) / rng, "body": (c - o) / rng,
                "size": rng / mr, "expansion": expansion, "turtle": turtle, "streak": self.streak[k],
                "pd": float(np.clip((price - self.bottom[k]) / span, -0.5, 1.5)) if span > 0 else 0.5,
                "swing_up": cap(np.min(self.h[self.sh[up]]) - price) if up.any() else CAP,
                "swing_dn": cap(price - np.max(self.l[self.sl[dn]])) if dn.any() else CAP,
                "prev_up": float(np.clip((h - price) / mr, -CAP, CAP)),
                "prev_dn": float(np.clip((price - l) / mr, -CAP, CAP)),
                "fvg_up": cap(np.min(self.g_lo[above]) - price) if above.any() else CAP,
                "fvg_dn": cap(price - np.max(self.g_hi[below])) if below.any() else CAP,
                "fvg_in": float(self.g_side[inside][-1]) if inside.any() else 0.0}


def state_table(market: str, days: pd.DataFrame) -> pd.DataFrame:
    """Every week's state at its open, its outcome (the close against the open) and the market."""
    fr = build_frames(days)
    frames = {tf: _Frame(fr[tf], tf) for tf in FRAMES}
    weeks = fr["W1"]
    rows = []
    for w in range(WARM_UP_WEEKS, len(weeks)):
        first = np.datetime64(weeks["first"].iat[w], "ns")
        price = float(weeks["open"].iat[w])
        ks = {tf: frames[tf].closed_before(first) for tf in FRAMES}
        if any(k < max(MEAN_N[tf], RANGE_N[tf]) + 2 for tf, k in ks.items()):
            continue
        prev_last, last = pd.Timestamp(weeks["last"].iat[w - 1]), pd.Timestamp(weeks["last"].iat[w])
        monday = pd.Timestamp(first) - pd.Timedelta(days=pd.Timestamp(first).dayofweek)
        row = {"market": market, "week": monday, "open": price, "close": float(weeks["close"].iat[w]),
               "quarter": (monday.month - 1) // 3 + 1, "month_of_quarter": (monday.month - 1) % 3 + 1,
               "week_of_month": (monday.day - 1) // 7 + 1, "new_month": float(last.month != prev_last.month),
               "new_quarter": float((last.month - 1) // 3 != (prev_last.month - 1) // 3 or last.year != prev_last.year),
               "gap": (price - float(weeks["close"].iat[w - 1])) / frames["W1"].mean[ks["W1"]]}
        for tf in FRAMES:
            row.update({f"{tf}_{x}": v for x, v in frames[tf].read(ks[tf], price).items()})
        rows.append(row)
    t = pd.DataFrame(rows)
    return t.assign(up=np.sign(t["close"] - t["open"]))


# ── the model and the calls ────────────────────────────────────────────────

def _weights(t: pd.DataFrame) -> np.ndarray:
    """Each market's up and down weeks weigh the same, so its drift can't be learned."""
    w = np.ones(len(t))
    for _, g in t.groupby("market"):
        for side in (1, -1):
            idx = g.index[g["up"] == side]
            w[t.index.get_indexer(idx)] = len(g) / (2 * max(len(idx), 1))
    return w


def fit_and_call(fit: pd.DataFrame, judged: pd.DataFrame, kind: str = "gbm") -> tuple[pd.DataFrame, pd.DataFrame, object]:
    """The model fitted on ``fit`` (weeks with a direction), its probabilities and calls on both: up at or above the
    fitted probabilities' 67th percentile, down at or below the 33rd."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.tree import DecisionTreeClassifier

    fit = fit[fit["up"] != 0].reset_index(drop=True)
    x, y, w = fit[list(FEATURES)].to_numpy(float), (fit["up"] > 0).astype(int).to_numpy(), _weights(fit)
    if kind == "gbm":
        model = HistGradientBoostingClassifier(**MODEL)
        model.fit(x, y, sample_weight=w)
    elif kind == "tree":
        model = DecisionTreeClassifier(max_depth=3, min_samples_leaf=300, random_state=0)
        model.fit(x, y, sample_weight=w)
    else:
        model = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        model.fit(x, y, logisticregression__sample_weight=w)
    p_fit = model.predict_proba(x)[:, 1]
    lo, hi = np.quantile(p_fit, [1 / 3, 2 / 3])

    def calls(t: pd.DataFrame) -> pd.DataFrame:
        p = model.predict_proba(t[list(FEATURES)].to_numpy(float))[:, 1]
        call = np.where(p >= hi, 1, np.where(p <= lo, -1, 0))
        return t.assign(p=p, call=call, every=np.where(p >= 0.5, 1, -1))

    return calls(fit), calls(judged.reset_index(drop=True)), model


def _scored(t: pd.DataFrame, col: str = "call") -> pd.DataFrame:
    """The calls of ``col`` with their hit and the market's drift over ``t``'s weeks (dojis left out)."""
    moved = t[t["up"] != 0]
    up_share = moved.groupby("market")["up"].apply(lambda s: float((s > 0).mean()))
    g = moved[moved[col] != 0]
    share = g["market"].map(up_share).to_numpy()
    base = np.where(g[col] > 0, share, 1 - share)
    hit = (g["up"] == g[col]).astype(float).to_numpy()
    return g.assign(hit=hit, base=base, excess=hit - base)


def judge(t: pd.DataFrame, col: str = "call", side: int = 0) -> dict:
    """The pass rule's numbers for ``t``'s calls of ``col``; ``side`` keeps only up (1) or down (-1) calls, with the
    drift still read over all of ``t``'s weeks."""
    g = _scored(t, col)
    if side:
        g = g[g[col] == side]
    if g.empty:
        return {"calls": 0}
    lo, hi = _interval(g["week"].to_numpy(), g["excess"].to_numpy(), 0.95)
    months = g["week"].dt.to_period("M").astype(str).to_numpy()
    mlo, mhi = _interval(months, g["excess"].to_numpy(), 0.95)
    per = {m: (float(x["excess"].mean()), len(x)) for m, x in g.groupby("market")}
    positive = sum(v > 0 for v, _ in per.values())
    excess = float(g["excess"].mean())
    return {"calls": len(g), "hit": float(g["hit"].mean()), "base": float(g["base"].mean()), "excess": excess,
            "lo": lo, "hi": hi, "month_lo": mlo, "month_hi": mhi, "per_market": per, "positive": positive,
            "passes": bool(excess > 0 and lo > 0 and positive >= MIN_MARKETS)}


def _pts(x: float) -> str:
    return "–" if not np.isfinite(x) else f"{100 * x:+.1f}"


def _line(name: str, r: dict) -> str:
    if not r.get("calls"):
        return f"| {name} | 0 | | | | | | |"
    return (f"| {name} | {r['calls']:,} | {r['hit']:.1%} | {r['base']:.1%} | {_pts(r['excess'])} | "
            f"[{_pts(r['lo'])}, {_pts(r['hi'])}] | {r['positive']}/9 | {'yes' if r.get('passes') else 'no'} |")


def main() -> None:
    from sklearn.inspection import permutation_importance
    from sklearn.tree import export_text

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--window", choices=["develop"], required=True)
    parser.parse_args()
    parts = []
    for market in MARKETS:
        t = state_table(market, load(market))
        parts.append(t)
        print(f"{market}: {len(t):,} weeks from {t['week'].iloc[0].date()}", flush=True)
    t = pd.concat(parts, ignore_index=True)
    fit = t[t["week"] < FIT_UNTIL]
    judged = t[(t["week"] >= JUDGE[0]) & (t["week"] < JUDGE[1])]
    OUT.mkdir(parents=True, exist_ok=True)
    fitted, called, model = fit_and_call(fit, judged, "gbm")
    called.to_parquet(OUT / "state_develop.parquet")
    r = judge(called)
    head = ["| Calls | n | Hit | Drift | Excess (pts) | 95% weeks | Markets > 0 | Passes |", "|---|---|---|---|---|---|---|---|"]
    lines = [f"Fitted on {len(fit[fit['up'] != 0]):,} weeks before {FIT_UNTIL.date()}; judged on "
             f"{len(judged[judged['up'] != 0]):,} weeks {JUDGE[0].date()} to 2022.", "", *head,
             _line("**H-Y: the model's top and bottom thirds**", r),
             _line("every week (above or below one half)", judge(called, "every")),
             _line("up calls", judge(called, side=1)), _line("down calls", judge(called, side=-1)),
             _line("in sample: the fitted weeks' thirds", judge(fitted)),
             f"\n95% interval over resampled months: [{_pts(r['month_lo'])}, {_pts(r['month_hi'])}]",
             "Excess per market: " + ", ".join(f"{m} {_pts(v)} ({n})" for m, (v, n) in r["per_market"].items())]
    for kind, name in (("tree", "depth-3 decision tree"), ("logit", "logistic regression")):
        f2, c2, m2 = fit_and_call(fit, judged, kind)
        lines += ["", f"**{name}**", *head, _line("its thirds, judged", judge(c2)), _line("in sample", judge(f2))]
        if kind == "tree":
            lines += ["", "```", export_text(m2, feature_names=list(FEATURES), decimals=3), "```"]
    judged_moved = called[called["up"] != 0]
    imp = permutation_importance(model, judged_moved[list(FEATURES)].to_numpy(float),
                                 (judged_moved["up"] > 0).astype(int).to_numpy(), scoring="roc_auc", n_repeats=5,
                                 random_state=0)
    order = np.argsort(-imp.importances_mean)[:12]
    lines += ["", "Permutation importance on the judged weeks (ROC AUC lost):",
              ", ".join(f"{FEATURES[i]} {imp.importances_mean[i]:+.4f}" for i in order)]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
