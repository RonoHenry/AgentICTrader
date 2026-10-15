"""The Model A record (context-engine Requirement 16, update 2026-10-15).

    python -m algo_research model-a [--instrument XAUUSD] [--set model_d1] [--universal]

Runs the Model A reader (``liquidity_engine.context.model_a``) over the exploration slice (AR-D3), per instrument
and frame set, beside its variants and two baselines that share its C and E rules:
- **CRT**: no F; any C2 that runs C1's extreme and closes back inside counts;
- **RANDOM_POI**: every POI moved 0.5-2 F average ranges, from a fixed seed.

It reports how often each state is reached and how it ends, and:
- **the premise**: once C2 has rejected, does price reach C1's opposite extreme before C2's extreme? That's
  Model A's C3 expansion, with many more cases than the fills. Its baseline is a coin flip from the same
  distances, d(C2's extreme) / (d(C1's opposite) + d(C2's extreme)), the chance a driftless walk gets there first.
- **after the fill**: TP1 and each SD level reached before the stop, and the R held to TP1 and to -2 SD.

Every rate carries a day-cluster interval (``algo_research.stats``). Descriptive: no verdict, no ledger row.
It feeds the review with the trader (task 312) and the next spec update.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from algo_research.stats import Bootstrap, series_table
from liquidity_engine.context.model_a import (EARLY, MODEL_A_VT, MODEL_SETS, UNIVERSAL_SETS, FrameSet, ModelAReader,
                                              Variant)

__all__ = ["ARMS", "Arm", "collect", "funnel", "load_instances", "premise", "read_instances", "record", "render",
           "summarise"]

STATES = ["FRAMED", "ARMED", "MANIPULATED", "REJECTED", "DISPLACED", "IN_OTE", "ENTERED", "TP1", "SD_1", "SD_2",
          "SD_2.5"]
ENDS = ["NO_MANIPULATION", "POI_FAILED", "NO_REJECTION", "RANGE_SPENT", "TOO_LARGE", "NO_ROOM", "RETRACE_INVALID",
        "MISSED", "EXPIRED", "STOPPED", "HORIZON", "TARGETS_DONE", "UNFINISHED"]
RESAMPLES = 2000


@dataclass(frozen=True)
class Arm:
    key: str
    label: str
    variant: Variant


_VOL = Variant(size_basis="SEASONAL", max_adr_used=MODEL_A_VT.max_adr_used, max_size_adr=MODEL_A_VT.max_size_adr,
               room=True)
#: Requirement 18: Model A plain, with time, with volatility, with both; and the two baselines under the same gates,
#: so the context still has to earn its edge where the time and volatility gates let it trade.
ARMS = (
    Arm("model", "Model A", Variant()),
    Arm("model_time", "+ time", Variant(phases=EARLY)),
    Arm("model_vol", "+ volatility", _VOL),
    Arm("model_vt", "+ time + volatility", MODEL_A_VT),
    Arm("crt", "CRT: no context", Variant(poi_mode="CRT")),
    Arm("crt_vt", "CRT + time + volatility", replace(MODEL_A_VT, poi_mode="CRT")),
    Arm("random_poi_vt", "Random POI + time + volatility", replace(MODEL_A_VT, poi_mode="RANDOM_POI", seed=20261015)),
)
#: Requirement 19: Model A and CRT under each thesis.
THESIS_ARMS = (
    Arm("model_vt_profile", "+ time + volatility, PROFILE thesis", replace(MODEL_A_VT, thesis="PROFILE")),
    Arm("model_vt_prev", "+ time + volatility, PREV_DAY thesis", replace(MODEL_A_VT, thesis="PREV_DAY")),
    Arm("model_vt_oracle", "+ time + volatility, ORACLE (hindsight)", replace(MODEL_A_VT, thesis="ORACLE")),
    Arm("model_profile", "Model A, PROFILE thesis", Variant(thesis="PROFILE")),
    Arm("model_oracle", "Model A, ORACLE (hindsight)", Variant(thesis="ORACLE")),
    Arm("crt_vt_profile", "CRT + time + volatility, PROFILE thesis", replace(MODEL_A_VT, poi_mode="CRT", thesis="PROFILE")),
    Arm("crt_vt_oracle", "CRT + time + volatility, ORACLE (hindsight)", replace(MODEL_A_VT, poi_mode="CRT", thesis="ORACLE")),
)
#: The variants of the first record (MA-D4, MA-D5) and the plain random-POI baseline: ``--all-arms``.
EXTRA_ARMS = (
    Arm("swing", "Model A, the leg runs to the swing low (MA-D5)", Variant(leg_end="SWING")),
    Arm("next_cisd", "Model A, the engine's next-candle CISD (MA-D4)", Variant(cisd="NEXT")),
    Arm("random_poi", "Random-POI baseline", Variant(poi_mode="RANDOM_POI", seed=20261015)),
)


def trading_date(wall: int) -> date:
    """The trading date of a New York wall second: days open at 17:00 the evening before."""
    return datetime.fromtimestamp(int(wall) + 7 * 3600, tz=timezone.utc).date()


def read_instances(m1: Tuple[np.ndarray, ...], frames: FrameSet, variant: Variant, start: int, end: int,
                   instrument: str, theses: Optional[Dict[int, int]] = None) -> pd.DataFrame:
    """Both sides' instances, with the trading date and the premise."""
    wall, o, h, l, c = m1
    if variant.thesis and theses is None:
        theses = daily_theses(m1, variant.thesis, instrument)
    rows = []
    for side in ("SHORT", "LONG"):
        rows += ModelAReader(frames, wall, o, h, l, c, side=side, variant=variant, theses=theses).run(start, end)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["instrument"] = instrument
    df["trading_date"] = [trading_date(s["FRAMED"]) for s in df["states"]]
    return premise(df, m1)


# ── the thesis (Requirement 19) ─────────────────────────────────────────

_DAY, _OPEN = 86400, 61200
THESES = ("PROFILE", "PREV_DAY", "ORACLE")


def day_directions(m1: Tuple[np.ndarray, ...]) -> Dict[int, int]:
    """Each trading day's direction (17:00 to 17:00 New York): +1 closed above its open, -1 below, 0 level."""
    wall, o, _h, _l, c = m1
    g = pd.DataFrame({"d": (np.asarray(wall) - _OPEN) // _DAY, "o": o, "c": c}).groupby("d").agg(o=("o", "first"), c=("c", "last"))
    return {int(k): int(v) for k, v in np.sign(g["c"] - g["o"]).items()}


def daily_theses(m1: Tuple[np.ndarray, ...], kind: str, instrument: str = "X") -> Dict[int, int]:
    """One thesis per trading day: +1 bullish, -1 bearish, 0 none.
    - PROFILE: the engine's D1 candle profile at the day's 17:00 open (liquidity-engine Requirement 21): the last
      closed week's trend toward its weekly objective, else the nearer untaken H4, D1 or W1 objective.
    - PREV_DAY: the day before closed that way (a naive baseline).
    - ORACLE: the day's own close against its open. Hindsight: an upper bound, never tradeable."""
    days = day_directions(m1)
    if kind == "ORACLE":
        return days
    if kind == "PREV_DAY":
        keys = sorted(days)
        return {d: days[p] for p, d in zip(keys, keys[1:])}
    if kind == "PROFILE":
        return _profile_theses(m1, instrument)
    raise ValueError(f"thesis: one of {', '.join(THESES)}")


def _profile_theses(m1: Tuple[np.ndarray, ...], instrument: str) -> Dict[int, int]:
    """The candle profile's direction at each trading day's open, from H4, D1 and W1 candles closed by then."""
    from algo_research.replay.timeframes import aggregate
    from liquidity_engine.models import BiasDirection, Candle, Timeframe
    from liquidity_engine.profile.candle_profile import CandleProfileAnalyzer
    wall, o, h, l, c = m1

    def candles(tf: str) -> List:
        b = aggregate(np.asarray(wall), o, h, l, c, tf)
        utc = pd.to_datetime(b["time"], unit="s").dt.tz_localize("America/New_York", ambiguous=True,
                                                                  nonexistent="shift_forward").dt.tz_convert("UTC")
        return [Candle(timestamp=t.to_pydatetime(), open=r.open, high=r.high, low=r.low, close=r.close,
                       timeframe=Timeframe[tf], instrument=instrument)
                for t, r in zip(utc, b.itertuples())]

    h4, d1, w1 = candles("H4"), candles("D1"), candles("W1")
    analyzer, out = CandleProfileAnalyzer(), {}
    for i, day in enumerate(d1):
        if i < 25:
            continue                                     # a few weeks of history first
        forming = day.model_copy(update={"high": day.open, "low": day.open, "close": day.open})   # its open only
        t = day.timestamp
        view = {Timeframe.D1: d1[max(0, i - 120):i] + [forming],
                Timeframe.W1: [w for w in w1 if w.timestamp < t][-60:],
                Timeframe.H4: [x for x in h4[max(0, 6 * i - 900):6 * i + 6] if x.timestamp < t][-300:]}
        profile = analyzer.analyze(view, t)
        if profile is None:
            continue
        d = int((int(pd.Timestamp(t).tz_convert("America/New_York").tz_localize(None).value // 10**9) - _OPEN) // _DAY)
        out[d] = 1 if profile.direction == BiasDirection.BULLISH else -1 if profile.direction == BiasDirection.BEARISH else 0
    return out


def thesis_accuracy(m1: Tuple[np.ndarray, ...], theses: Dict[int, int], start: int, end: int, seed: int = 17) -> dict:
    """How often the thesis named the day's direction, among the days it named one, with a day-bootstrap interval;
    and the share of days it named one at all."""
    days = day_directions(m1)
    lo_d, hi_d = (start - _OPEN) // _DAY, (end - _OPEN) // _DAY
    named = [(d, v) for d, v in theses.items() if lo_d <= d < hi_d and v != 0 and days.get(d, 0) != 0]
    all_days = [d for d in days if lo_d <= d < hi_d and days[d] != 0]
    if not named:
        return {"days": len(all_days), "named": 0, "right": np.nan, "lo": np.nan, "hi": np.nan}
    hit = np.array([1.0 if v == days[d] else 0.0 for d, v in named])
    rng = np.random.default_rng(seed)
    boots = rng.choice(hit, size=(RESAMPLES, len(hit)), replace=True).mean(axis=1)
    return {"days": len(all_days), "named": len(named), "right": float(hit.mean()),
            "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5))}


def premise(df: pd.DataFrame, m1: Tuple[np.ndarray, ...]) -> pd.DataFrame:
    """For each instance C2 rejected: from C2's close, whether C1's opposite extreme comes before C2's extreme
    (True / False; None when neither by the end of the F candle), the coin flip from those distances, and whether
    C2 had already reached C1's opposite extreme itself."""
    from algo_research.replay.timeframes import bucket, seconds_of
    wall, _o, h, l, _c = m1
    first, coin, inside = [], [], []
    for row in df.itertuples():
        t0 = row.states.get("REJECTED") if isinstance(row.states, dict) else None
        if t0 is None:
            first.append(None); coin.append(np.nan); inside.append(None)
            continue
        short = row.side == "SHORT"
        target, stop = row.c1_opposite, row.c2_extreme
        f_end = int(bucket(np.array([t0 - 1], dtype=np.int64), row.f)[0]) + seconds_of(row.f)
        i0 = int(np.searchsorted(wall, t0, side="left"))
        i1 = int(np.searchsorted(wall, max(f_end, t0 + 1), side="left"))
        c2_lo = int(np.searchsorted(wall, t0 - seconds_of(row.c), side="left"))
        c2_reached = bool((l[c2_lo:i0] <= target).any()) if short else bool((h[c2_lo:i0] >= target).any())
        inside.append(c2_reached)
        hit_t = (l[i0:i1] <= target) if short else (h[i0:i1] >= target)
        hit_s = (h[i0:i1] > stop) if short else (l[i0:i1] < stop)
        a = int(np.argmax(hit_t)) if hit_t.any() else None
        b = int(np.argmax(hit_s)) if hit_s.any() else None
        if a is None and b is None:
            first.append(None)
        elif b is None or (a is not None and a < b):
            first.append(True)
        else:
            first.append(False)                      # the stop first, or both in one minute: the stop
        close = _close_at(m1, i0)
        d_t, d_s = abs(close - target), abs(stop - close)
        coin.append(d_s / (d_t + d_s) if d_t + d_s > 0 else np.nan)
    df = df.copy()
    df["premise"], df["premise_coin"], df["c1_taken_in_c2"] = first, coin, inside
    return df


def _close_at(m1, i0: int) -> float:
    """The last close before index ``i0``: price at C2's close."""
    return float(m1[4][max(0, i0 - 1)])


# ── the numbers ───────────────────────────────────────────────────────────

def funnel(df: pd.DataFrame) -> Dict[str, int]:
    """How many instances reached each state, and how many ended each way."""
    reached = {s: 0 for s in STATES}
    for states in df.get("states", []):
        for s in states:
            if s in reached:
                reached[s] += 1
    ends = df["end"].value_counts().to_dict() if "end" in df else {}
    return {**reached, **{f"end:{e}": int(ends.get(e, 0)) for e in ENDS}}


def _interval(dates: Sequence, sums: np.ndarray, counts: np.ndarray, seed: int) -> Tuple[float, float, float]:
    """The ratio sum/count over the instances, with its day-cluster bootstrap interval."""
    if counts.sum() == 0:
        return np.nan, np.nan, np.nan
    table = series_table(dates, ["x"] * len(dates), {"s": (sums, counts)})
    ratios = Bootstrap(table, RESAMPLES, seed).ratios(table, "s")
    ratios = ratios[np.isfinite(ratios)]
    point = float(sums.sum() / counts.sum())
    if not len(ratios):
        return point, np.nan, np.nan
    return point, float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))


def rate(df: pd.DataFrame, among: pd.Series, hit: pd.Series, seed: int = 7) -> dict:
    """The share of ``among`` where ``hit``, with its day-cluster interval."""
    among = among.fillna(False).astype(bool)
    n = int(among.sum())
    if not n:
        return {"n": 0, "k": 0, "rate": np.nan, "lo": np.nan, "hi": np.nan}
    sub = df[among]
    k = hit[among].fillna(False).astype(float).to_numpy()
    point, lo, hi = _interval(list(sub["trading_date"]), k, np.ones(n), seed)
    return {"n": n, "k": int(k.sum()), "rate": point, "lo": lo, "hi": hi}


def mean(df: pd.DataFrame, col: str, among: Optional[pd.Series] = None, seed: int = 11) -> dict:
    vals = df[col] if among is None else df.loc[among.fillna(False).astype(bool), col]
    vals = vals.dropna()
    if vals.empty:
        return {"n": 0, "mean": np.nan, "lo": np.nan, "hi": np.nan}
    point, lo, hi = _interval(list(df.loc[vals.index, "trading_date"]), vals.to_numpy(float), np.ones(len(vals)), seed)
    return {"n": int(len(vals)), "mean": point, "lo": lo, "hi": hi}


def premise_edge(df: pd.DataFrame, seed: int = 13) -> dict:
    """The premise against its coin flip, paired date by date: (rate - coin) with its interval."""
    sub = df[df["premise"].notna()] if "premise" in df else df.iloc[:0]
    if sub.empty:
        return {"n": 0, "rate": np.nan, "coin": np.nan, "edge": np.nan, "lo": np.nan, "hi": np.nan}
    hit = sub["premise"].astype(float).to_numpy()
    coin = sub["premise_coin"].to_numpy(float)
    ones = np.ones(len(sub))
    table = series_table(list(sub["trading_date"]), ["x"] * len(sub), {"hit": (hit, ones), "coin": (coin, ones)})
    boot = Bootstrap(table, RESAMPLES, seed)
    diff = boot.ratios(table, "hit") - boot.ratios(table, "coin")
    diff = diff[np.isfinite(diff)]
    return {"n": int(len(sub)), "rate": float(hit.mean()), "coin": float(np.nanmean(coin)),
            "edge": float(hit.mean() - np.nanmean(coin)),
            "lo": float(np.percentile(diff, 2.5)) if len(diff) else np.nan,
            "hi": float(np.percentile(diff, 97.5)) if len(diff) else np.nan}


def summarise(df: pd.DataFrame) -> dict:
    """The funnel, the step rates, the premise, and the outcomes after the fill."""
    if df.empty:
        return {"n": 0, "funnel": funnel(df)}
    reached = lambda s: df["states"].map(lambda st: s in st)  # noqa: E731
    entered = reached("ENTERED")
    hits = lambda key: df["hits"].map(lambda hs: key in hs)    # noqa: E731
    return {
        "n": len(df), "funnel": funnel(df),
        "steps": {
            "MANIPULATED of ARMED": rate(df, reached("ARMED"), reached("MANIPULATED")),
            "REJECTED of MANIPULATED": rate(df, reached("MANIPULATED"), reached("REJECTED")),
            "DISPLACED of REJECTED": rate(df, reached("REJECTED"), reached("DISPLACED")),
            "ENTERED of REJECTED and DISPLACED": rate(df, reached("REJECTED") & reached("DISPLACED"), entered),
        },
        "premise": premise_edge(df),
        "c1_taken_in_c2": rate(df, df["c1_taken_in_c2"].notna(), df["c1_taken_in_c2"] == True),  # noqa: E712
        "after_fill": {
            "TP1 before the stop": rate(df, entered, hits("tp1")),
            "-1 SD before the stop": rate(df, entered, hits("sd1")),
            "-2 SD before the stop": rate(df, entered, hits("sd2")),
            "-2.5 SD before the stop": rate(df, entered, hits("sd25")),
            "R held to TP1": mean(df, "r_tp1", entered),
            "R held to -2 SD": mean(df, "r_sd2", entered),
        },
    }


def breakdown(df: pd.DataFrame, by: str) -> List[Tuple[str, dict]]:
    """The premise and the fills per value of ``by``, among instances C2 rejected."""
    if df.empty or by not in df:
        return []
    sub = df[df["states"].map(lambda st: "REJECTED" in st)]
    out = []
    key = sub[by].map(lambda v: "None" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
    for value, part in sub.groupby(key, sort=True):
        out.append((value, {"premise": premise_edge(part),
                            "fills": rate(part, pd.Series(True, index=part.index), part["states"].map(lambda st: "ENTERED" in st))}))
    return out


# ── the report ────────────────────────────────────────────────────────────

def _pct(x) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{100 * x:.0f}%"


def _ci(d: dict, key: str = "rate", pct: bool = True) -> str:
    v, lo, hi = d.get(key), d.get("lo"), d.get("hi")
    if v is None or not np.isfinite(v):
        return "–"
    f = _pct if pct else (lambda x: "–" if not np.isfinite(x) else f"{x:+.2f}")
    return f"{f(v)} [{f(lo)}, {f(hi)}]"


def render_set(title: str, results: Dict[str, Tuple[Arm, pd.DataFrame, dict]]) -> str:
    lines = [f"### {title}", ""]
    arms = list(results.values())
    lines += ["| State reached | " + " | ".join(a.label for a, _, _ in arms) + " |",
              "|---|" + "---:|" * len(arms)]
    for s in STATES:
        lines.append(f"| {s} | " + " | ".join(str(r["funnel"].get(s, 0)) for _, _, r in arms) + " |")
    lines += ["", "| How it ended | " + " | ".join(a.label for a, _, _ in arms) + " |", "|---|" + "---:|" * len(arms)]
    for e in ENDS:
        if any(r["funnel"].get(f"end:{e}", 0) for _, _, r in arms):
            lines.append(f"| {e} | " + " | ".join(str(r["funnel"].get(f"end:{e}", 0)) for _, _, r in arms) + " |")
    lines += ["", "| Measure | " + " | ".join(a.label for a, _, _ in arms) + " |", "|---|" + "---|" * len(arms)]
    step_names = list(next((r["steps"] for _, _, r in arms if "steps" in r), {}).keys())
    for name in step_names:
        lines.append(f"| {name} | " + " | ".join(
            f"{_ci(r['steps'][name])} (n {r['steps'][name]['n']})" if "steps" in r else "–" for _, _, r in arms) + " |")
    lines.append("| **Premise**: C1's opposite extreme before C2's extreme | " + " | ".join(
        f"{_pct(r['premise']['rate'])} vs coin {_pct(r['premise']['coin'])}: **{_ci({'rate': r['premise']['edge'], 'lo': r['premise']['lo'], 'hi': r['premise']['hi']})}** (n {r['premise']['n']})"
        if "premise" in r else "–" for _, _, r in arms) + " |")
    lines.append("| C2 had already reached C1's opposite extreme | " + " | ".join(
        f"{_ci(r['c1_taken_in_c2'])}" if "c1_taken_in_c2" in r else "–" for _, _, r in arms) + " |")
    after = list(next((r["after_fill"] for _, _, r in arms if "after_fill" in r), {}).keys())
    for name in after:
        cells = []
        for _, _, r in arms:
            d = r.get("after_fill", {}).get(name)
            if d is None:
                cells.append("–")
            elif "mean" in d:
                cells.append(f"{_ci(d, 'mean', pct=False)} (n {d['n']})")
            else:
                cells.append(f"{_ci(d)} (n {d['n']})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def render_breakdowns(df: pd.DataFrame) -> str:
    lines = []
    for by, title in (("phase", "C2's phase of the day (MA-D13)"), ("time_sync", "C2 in the trader's time window (MA-D9)"),
                      ("inducement", "Inducement (MA-D3)"),
                      ("poi_kind", "The POI's kind (MA-D2)"), ("side", "Side")):
        rows = breakdown(df, by)
        if not rows:
            continue
        lines += ["", f"*{title}*, among C2s that rejected:", "", "| | Premise vs coin | Filled |", "|---|---|---|"]
        for value, d in rows:
            p = d["premise"]
            lines.append(f"| {value} | {_pct(p['rate'])} vs {_pct(p['coin'])}: "
                         f"{_ci({'rate': p['edge'], 'lo': p['lo'], 'hi': p['hi']})} (n {p['n']}) | "
                         f"{_ci(d['fills'])} (n {d['fills']['n']}) |")
    return "\n".join(lines) + "\n"


_INTRO = ["**How to read it.**",
          "- The funnel counts instances: each closed C candle in context starts one.",
          "- **The premise:** once C2 has rejected, how often price reaches C1's opposite extreme before C2's "
          "extreme, within the F candle. It's compared with a coin flip from the same distances.",
          "  - The interval is that difference, paired by trading date.",
          "  - A lower bound above zero means the step carries information.",
          "- **After the fill:** the outcomes of the few that reach the OTE and fill.",
          "- **The baselines** read the same C and E rules. CRT has no F context; the random-POI baseline "
          "moves every POI.", ""]


def collect(m1_by_instrument: Dict[str, Tuple[np.ndarray, ...]], sets: Iterable[FrameSet], start: int, end: int,
            arms: Sequence[Arm] = ARMS, progress=print) -> pd.DataFrame:
    """Every instance read, per instrument, set and arm."""
    everything = []
    for inst, m1 in m1_by_instrument.items():
        theses = {kind: daily_theses(m1, kind, inst) for kind in {a.variant.thesis for a in arms if a.variant.thesis}}
        for fs in sets:
            for arm in arms:
                progress(f"{inst} {fs.name} {arm.key}")
                df = read_instances(m1, fs, arm.variant, start, end, inst, theses.get(arm.variant.thesis))
                if not df.empty:
                    df["arm"], df["set"] = arm.key, fs.name
                    everything.append(df)
    with warnings.catch_warnings():                 # arms without fills have all-empty outcome columns
        warnings.simplefilter("ignore", FutureWarning)
        return pd.concat(everything, ignore_index=True) if everything else pd.DataFrame()


def _edge(p: dict) -> str:
    if not p.get("n"):
        return "–"
    return f"{100 * p['edge']:+.0f}% [{100 * p['lo']:+.0f}, {100 * p['hi']:+.0f}] (n {p['n']})"


def render(instances: pd.DataFrame, sets: Sequence[FrameSet], arms: Sequence[Arm] = ARMS,
           meta: Optional[dict] = None, thesis_rows: Sequence[Tuple[str, str, dict]] = ()) -> str:
    """The report, from the instances: a summary table first, then each instrument and set in full."""
    meta = meta or {}
    parts = ["# The Model A record", "",
             "Context-engine Requirement 16 (update 2026-10-15). Descriptive: no verdict and no ledger row. "
             "It feeds the review with the trader.", "",
             *[f"- **{k}:** {v}" for k, v in meta.items()], "", *_INTRO]
    instruments = list(dict.fromkeys(instances["instrument"])) if not instances.empty else []
    by = {}
    for inst in instruments:
        for fs in sets:
            for arm in arms:
                part = instances[(instances["instrument"] == inst) & (instances["set"] == fs.name)
                                 & (instances["arm"] == arm.key)] if not instances.empty else instances
                by[inst, fs.name, arm.key] = (arm, part, summarise(part))
    keys = [a.key for a in arms]
    if thesis_rows:
        parts += ["## The theses on their own", "",
                  "How often each thesis named the trading day's direction (its D1 candle closing above or below its "
                  "open), among the days it named one; a coin flip is 50%. ORACLE is that direction itself: hindsight, "
                  "the upper bound.", "", "| Instrument | Thesis | Days named | Right |", "|---|---|---:|---|"]
        for inst, kind, a in thesis_rows:
            right = "–" if not a["named"] else f"{a['right']:.0%} [{a['lo']:.0%}, {a['hi']:.0%}]"
            parts.append(f"| {inst} | {kind} | {a['named']} of {a['days']} | {right} |")
        parts.append("")
    parts += ["## Summary: the premise against its coin flip", "",
              "Once C2 has rejected: C1's opposite extreme before C2's extreme, minus the coin flip from the same "
              "distances, with its day-cluster interval. The last arm with fills gives the fills and the R held to TP1.", "",
              "| Instrument | Frame set | " + " | ".join(a.label for a in arms) + " | Fills | R held to TP1 |",
              "|---|---|" + "---|" * len(arms) + "---:|---|"]
    lead = next((k for k in ("model_vt", "model_vt_profile") if k in keys), keys[0])
    for inst in instruments:
        for fs in sets:
            cells = [_edge(by[inst, fs.name, k][2].get("premise", {})) for k in keys]
            m = by[inst, fs.name, lead][2]
            fills = m.get("funnel", {}).get("ENTERED", 0)
            r_tp1 = m.get("after_fill", {}).get("R held to TP1", {})
            parts.append(f"| {inst} | {fs.name} ({fs.f}/{fs.c}/{fs.e}) | " + " | ".join(cells) +
                         f" | {fills} | {_ci(r_tp1, 'mean', pct=False) if r_tp1.get('n') else '–'} |")
    parts += ["", f"*Fills and R are for {next(a.label for a in arms if a.key == lead)}.*", ""]
    for inst in instruments:
        parts.append(f"## {inst}\n")
        for fs in sets:
            results = {arm.key: by[inst, fs.name, arm.key] for arm in arms}
            parts.append(render_set(f"{fs.name}: F {fs.f}, C {fs.c}, E {fs.e}", results))
            for key in ("model", "model_vt", "model_vt_profile", "model_vt_oracle"):
                part = results[key][1] if key in results else pd.DataFrame()
                if not part.empty:
                    parts.append(f"\n**Breakdowns: {results[key][0].label}**\n")
                    parts.append(render_breakdowns(part))
    return "\n".join(parts)


def record(m1_by_instrument: Dict[str, Tuple[np.ndarray, ...]], sets: Iterable[FrameSet], start: int, end: int,
           arms: Sequence[Arm] = ARMS, meta: Optional[dict] = None, progress=print) -> Tuple[str, pd.DataFrame]:
    """The report and every instance read, per instrument, set and arm."""
    sets = list(sets)
    instances = collect(m1_by_instrument, sets, start, end, arms, progress)
    kinds = sorted({a.variant.thesis for a in arms if a.variant.thesis})
    rows = [(inst, kind, thesis_accuracy(m1, daily_theses(m1, kind, inst), start, end))
            for inst, m1 in m1_by_instrument.items() for kind in kinds]
    return render(instances, sets, arms, meta, rows), instances


def load_instances(path: Path) -> pd.DataFrame:
    """Instances saved by ``python -m algo_research model-a``, ready to render again."""
    parts = [chunk.drop(columns=["events"], errors="ignore")       # the report doesn't read the event lists
             for chunk in pd.read_json(path, orient="records", lines=True, chunksize=50_000)]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not df.empty:
        df["trading_date"] = pd.to_datetime(df["trading_date"]).dt.date
        for col in ("states", "hits"):
            df[col] = df[col].map(lambda x: x if isinstance(x, dict) else {})
        for col in ("time_sync", "premise", "c1_taken_in_c2"):          # JSON gives back 0.0 and NaN for these
            if col in df:
                df[col] = df[col].map(lambda x: None if x is None or (isinstance(x, float) and np.isnan(x)) else bool(x))
                df[col] = df[col].astype(object)
    return df
