"""The context at a swing (algo-research update 2026-10g, Requirement 25).

What was true when each swing formed, as columns on the swing table. Every value is known when the swing is
known (Property 1). Lows are read as they are, and highs on the prices turned upside down, so each rule exists
once.

**Arrays traded into** (25.1): ``arr_<tf>_<name>``, for tf M15 to W1 and name FVG, IFVG, OB or BRK.
- Only arrays of the swing's timeframe and above count. They must face the turn (support for a low), have
  formed by the extreme bar's open, and have a range the extreme bar overlapped.
- The value is the deepest reach: ``edge`` (inside, short of the CE or MT), ``mid`` (at or beyond it),
  ``through`` (beyond the far edge).
- ``arr_any`` is any of them; ``arr_htf_any`` is any above the swing's timeframe.

**Liquidity taken** (25.2): ``liq_*``. A level counts when three things hold: it was known before the
extreme's minute; it was untaken from then until the extreme bar opened; and the extreme went beyond it.
- ``pd``, ``pw``, ``pm``: the previous trading day's, week's and month's extremes.
- ``asia``: the trading date's 20:00–00:00 New York range (``asian_pools``, LE-D12), known at 00:00.
- ``london``: 00:00–07:00 New York, known at 07:00.
- ``htf_swing``: an untaken three-candle swing of the next timeframe up.
- ``equal``: two untaken three-candle swings of the swing's own timeframe, known by the bar's open, within
  0.1 of its average range of each other, both taken.

**Dealing range** (25.3): ``pd`` is the extreme's place in the next timeframe's range, in real prices (0 at its
last untaken three-candle swing low, 1 at its last untaken swing high, as the extreme bar opened).
``pd_zone`` reads it for the swing's side: discount, premium, or beyond the range on the swing's own side.
``pd_aligned`` is a low in discount or beyond, or a high in premium or beyond.

**Time** (25.4): ``ny_hour``, ``session`` (asia 17–00, london 00–07, ny_am 07–12, ny_pm 12–17), ``killzone``,
``h4_index`` and ``weekday``, all at the extreme's minute.

**Anatomy** (25.5):
- ``turtle_soup``: the extreme bar swept the previous bar's extreme and closed back inside.
- ``wick_share``: on the swept side.
- ``displacement``: the confirming bar's body ÷ the average range. The confirming bar is C3, or the engulfing
  bar itself.
- ``closes_beyond``: the confirming close beyond the extreme bar's other extreme (``engulf_full`` for an
  engulfing swing).
- ``own_fvg``: C1 and C3 leave a gap (none for an engulfing swing: its third bar isn't known yet).

    table = build_context(frame, swings, arrays)     # the swing table with the context columns

Validates: Requirement 25 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from algo_research.atlas.arrays import ARRAY_TIMEFRAMES
from algo_research.atlas.swings import NEXT_TF, _first
from algo_research.frame import InstrumentFrame, calendar_columns
from liquidity_engine.context.measures import mirror
from liquidity_engine.models import Timeframe

__all__ = ["ARRAY_NAMES", "CONTEXT_COLUMNS", "LIQUIDITY", "build_context", "facing_depths", "pd_zone"]

ARRAY_NAMES = ("FVG", "IFVG", "OB", "BRK")
LIQUIDITY = ("pd", "pw", "pm", "asia", "london", "htf_swing", "equal")
_TFS = [tf.value for tf in ARRAY_TIMEFRAMES]
CONTEXT_COLUMNS = ([f"arr_{tf}_{name}" for tf in _TFS for name in ARRAY_NAMES] + ["arr_any", "arr_htf_any"]
                   + [f"liq_{name}" for name in LIQUIDITY]
                   + ["pd", "pd_zone", "pd_aligned", "ny_hour", "session", "killzone", "h4_index", "weekday",
                      "turtle_soup", "wick_share", "displacement", "closes_beyond", "own_fvg"])

_DEPTH = {"edge": 1, "mid": 2, "through": 3}
_EQUAL_SHARE = 0.1                     # equal lows: within a tenth of the timeframe's average range
_NEVER = np.iinfo(np.int64).max
_NAT = np.iinfo(np.int64).min


def _ns(times) -> np.ndarray:
    index = pd.DatetimeIndex(times)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return index.tz_localize(None).to_numpy("datetime64[ns]").view(np.int64)


# ── arrays (25.1) ──────────────────────────────────────────────────────────

class _Arrays:
    """Arrays as a low sees them (a high reads them upside down), as plain numpy columns."""

    def __init__(self, arrays: pd.DataFrame, side: str) -> None:
        flip = side == "high"
        low, high = arrays["low"].to_numpy(float), arrays["high"].to_numpy(float)
        self.low, self.high = (-high, -low) if flip else (low, high)
        self.mid = -arrays["mid"].to_numpy(float) if flip else arrays["mid"].to_numpy(float)
        self.direction = (-1 if flip else 1) * arrays["direction"].to_numpy()
        self.formed, self.flipped = _ns(arrays["formed_at"]), _ns(arrays["flipped_at"])
        self.tf = arrays["tf"].to_numpy(dtype=object)
        self.is_fvg = (arrays["kind"] == "FVG").to_numpy()

    def depths(self, open_ns: int, extreme: float, bar_high: float, allowed: np.ndarray) -> dict:
        """{(tf, name): deepest depth} of the supporting arrays a low's extreme bar traded into."""
        hit = allowed & (self.formed <= open_ns) & (extreme <= self.high) & (bar_high >= self.low)
        if not hit.any():
            return {}
        idx = np.flatnonzero(hit)
        flipped = (self.flipped[idx] != _NAT) & (self.flipped[idx] <= open_ns)
        facing = np.where(flipped, -self.direction[idx], self.direction[idx])
        out: dict = {}
        for n, f in zip(idx[facing == 1], flipped[facing == 1]):
            depth = "edge" if extreme > self.mid[n] else ("mid" if extreme >= self.low[n] else "through")
            name = ("IFVG" if f else "FVG") if self.is_fvg[n] else ("BRK" if f else "OB")
            key = (self.tf[n], name)
            if _DEPTH[depth] > _DEPTH.get(out.get(key), 0):
                out[key] = depth
        return out


def facing_depths(arrays: pd.DataFrame, open_at, extreme: float, bar_high: float, side: str = "low") -> dict:
    """{(tf, name): depth} of the arrays facing a swing that its extreme bar (opened at ``open_at``, reaching
    ``extreme``, with ``bar_high`` its other extreme) traded into, the deepest of each (Req 25.1). For a high,
    ``extreme`` is the bar's high and ``bar_high`` its low, in real prices."""
    view = _Arrays(arrays, side)
    sign = 1.0 if side == "low" else -1.0
    return view.depths(_ns([open_at])[0], sign * extreme, sign * bar_high, np.ones(len(arrays), bool))


def _array_columns(view: _Arrays, tf: Timeframe, open_ns: np.ndarray, extreme: np.ndarray,
                   bar_high: np.ndarray) -> dict:
    allowed = np.isin(view.tf, _TFS[_TFS.index(tf.value):])
    n = len(extreme)
    columns = {f"arr_{t}_{name}": np.full(n, None, dtype=object) for t in _TFS for name in ARRAY_NAMES}
    any_, htf = np.zeros(n, bool), np.zeros(n, bool)
    for s in range(n):
        for (t, name), depth in view.depths(open_ns[s], extreme[s], bar_high[s], allowed).items():
            columns[f"arr_{t}_{name}"][s] = depth
            any_[s] = True
            htf[s] |= t != tf.value
    return {**columns, "arr_any": any_, "arr_htf_any": htf}


# ── levels and when they were taken (25.2, 25.3) ───────────────────────────

def _taken_at(levels: np.ndarray, known: np.ndarray, m1_t: np.ndarray, m1_l: np.ndarray) -> np.ndarray:
    """For oriented levels (read as lows): the open time of the first M1 bar at or after each level was known
    whose low went below it; never (int64 max) if none."""
    out = np.full(len(levels), _NEVER, dtype=np.int64)
    for n, (level, k) in enumerate(zip(levels, known)):
        if not np.isfinite(level) or k == _NEVER:
            continue
        idx = _first(m1_l, int(np.searchsorted(m1_t, k, "left")), len(m1_t), float(level), below=True)
        if idx >= 0:
            out[n] = m1_t[idx]
    return out


def _period_levels(bars: Optional[pd.DataFrame], lows: Optional[np.ndarray], t_ns: np.ndarray):
    """For instants ``t_ns``: the previous bar's (oriented) low and when it was known (the current bar's open)."""
    if bars is None or bars.empty:
        return np.full(len(t_ns), np.nan), np.full(len(t_ns), _NEVER)
    close = _ns(bars["close_time"])
    prev = np.searchsorted(close, t_ns, "right") - 1                 # the bar before the one containing t
    ok = prev >= 0
    level = np.where(ok, lows[np.clip(prev, 0, None)], np.nan)
    known = np.where(ok, close[np.clip(prev, 0, None)], _NEVER)
    return level, known


def _trading_months(times_ns: np.ndarray) -> np.ndarray:
    dates = calendar_columns(pd.DatetimeIndex(times_ns).tz_localize("UTC"))["trading_date"]
    return (dates.dt.year * 12 + dates.dt.month).to_numpy()


def _month_levels(d1: Optional[pd.DataFrame], lows: Optional[np.ndarray], t_ns: np.ndarray):
    """The previous trading month's (oriented) low, and the current month's first open (when it is known)."""
    if d1 is None or d1.empty:
        return np.full(len(t_ns), np.nan), np.full(len(t_ns), _NEVER)
    opens = _ns(d1["time"])
    month = _trading_months(opens)
    month_low = pd.Series(lows).groupby(month).min()
    first_open = pd.Series(opens).groupby(month).min().astype("Int64")
    t_month = _trading_months(t_ns)
    level = month_low.reindex(t_month - 1).to_numpy(float)
    known = first_open.reindex(t_month).fillna(_NEVER).to_numpy(np.int64)        # kept as integers: exact ns
    return level, known


def _session_levels(h1: Optional[pd.DataFrame], lows: Optional[np.ndarray], t_ns: np.ndarray, first: int, end: int):
    """The (oriented) low of the instant's trading date's H1 bars starting in [first, end) New York minutes
    (wrapping past midnight when first > end), known at the session's last close."""
    if h1 is None or h1.empty:
        return np.full(len(t_ns), np.nan), np.full(len(t_ns), _NEVER)
    cal = calendar_columns(pd.DatetimeIndex(h1["time"]))
    minute = cal["ny_minute"].to_numpy()
    in_session = (minute >= first) & (minute < end) if first < end else (minute >= first) | (minute < end)
    dates = cal["trading_date"].to_numpy()[in_session]
    session_low = pd.Series(lows[in_session]).groupby(dates).min()
    session_end = pd.Series(_ns(h1["close_time"])[in_session]).groupby(dates).max().astype("Int64")
    t_dates = calendar_columns(pd.DatetimeIndex(t_ns).tz_localize("UTC"))["trading_date"].to_numpy()
    return (session_low.reindex(t_dates).to_numpy(float),
            session_end.reindex(t_dates).fillna(_NEVER).to_numpy(np.int64))


def _swing_levels(swings: pd.DataFrame, side: str, m1_t: np.ndarray, m1_l: np.ndarray):
    """A side's three-candle swings as oriented levels: (level, known ns, taken ns), with ``m1_l`` oriented."""
    rows = swings[(swings["side"] == side) & (swings["type"] == "three")]
    level = (1.0 if side == "low" else -1.0) * rows["extreme"].to_numpy(float)
    known = _ns(rows["known_at"])
    return level, known, _taken_at(level, known, m1_t, m1_l)


def pd_zone(side: str, pd_value) -> Optional[str]:
    """The dealing-range zone of a swing's extreme, read for its side: a low is in discount below 0.5, beyond
    under 0; a high in premium above 0.5, beyond over 1."""
    if pd_value is None or not np.isfinite(pd_value):
        return None
    if side == "low":
        return "beyond" if pd_value < 0 else ("discount" if pd_value < 0.5 else "premium")
    return "beyond" if pd_value > 1 else ("premium" if pd_value > 0.5 else "discount")


def _last_untaken(level: np.ndarray, known: np.ndarray, taken: np.ndarray, at_ns: int) -> float:
    """The most recent level known by ``at_ns`` and not yet taken then; NaN if none."""
    ok = np.flatnonzero((known <= at_ns) & (taken >= at_ns))
    return float(level[ok[-1]]) if len(ok) else np.nan


# ── the table ──────────────────────────────────────────────────────────────

def _session(minute: np.ndarray) -> np.ndarray:
    return np.select([minute >= 17 * 60, minute < 7 * 60, minute < 12 * 60], ["asia", "london", "ny_am"], "ny_pm")


def _side_context(frame: InstrumentFrame, swings: pd.DataFrame, all_swings: pd.DataFrame, arrays: _Arrays,
                  tf: Timeframe, side: str, ranges: Optional[tuple]) -> pd.DataFrame:
    sign = 1.0 if side == "low" else -1.0
    bars = frame.bars[tf]
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    if side == "high":
        o, h, l, c = mirror(o, h, l, c)
    m1_t = frame.arrays["time"]
    m1_l = frame.arrays["low"] if side == "low" else -frame.arrays["high"]

    n = len(swings)
    extreme = sign * swings["extreme"].to_numpy(float)
    open_ns, ext_ns = _ns(swings["extreme_bar"]), _ns(swings["extreme_time"])
    i = np.searchsorted(_ns(bars["time"]), open_ns, "left")
    is_three = (swings["type"] == "three").to_numpy()
    conf = np.where(is_three, np.minimum(i + 1, len(c) - 1), i)
    avg = swings["avg_range"].to_numpy(float)
    out = _array_columns(arrays, tf, open_ns, extreme, h[i])

    # Period and session levels: untaken from when they were known until the extreme bar opened.
    def oriented_lows(b):
        if b is None or b.empty:
            return None
        return b["low"].to_numpy(float) if side == "low" else -b["high"].to_numpy(float)

    d1, w1, h1 = (frame.bars.get(t) for t in (Timeframe.D1, Timeframe.W1, Timeframe.H1))
    periods = {
        "pd": _period_levels(d1, oriented_lows(d1), ext_ns),
        "pw": _period_levels(w1, oriented_lows(w1), ext_ns),
        "pm": _month_levels(d1, oriented_lows(d1), ext_ns),
        "asia": _session_levels(h1, oriented_lows(h1), ext_ns, 20 * 60, 0),
        "london": _session_levels(h1, oriented_lows(h1), ext_ns, 0, 7 * 60),
    }
    for name, (level, known) in periods.items():
        taken = np.zeros(n, bool)
        for s in range(n):
            if np.isfinite(level[s]) and known[s] < ext_ns[s] and extreme[s] < level[s]:
                lo, hi = np.searchsorted(m1_t, known[s], "left"), np.searchsorted(m1_t, open_ns[s], "left")
                taken[s] = hi <= lo or m1_l[lo:hi].min() >= level[s]
        out[f"liq_{name}"] = taken

    # Swing levels: taken by this extreme when known before it, untaken at the bar's open, and beyond it.
    nxt = NEXT_TF.get(tf)
    htf = (_swing_levels(all_swings[all_swings["tf"] == nxt.value], side, m1_t, m1_l) if nxt
           else (np.empty(0), np.empty(0, np.int64), np.empty(0, np.int64)))
    own = _swing_levels(all_swings[all_swings["tf"] == tf.value], side, m1_t, m1_l)
    liq_htf, liq_equal = np.zeros(n, bool), np.zeros(n, bool)
    for s in range(n):
        lv, k, tk = htf
        liq_htf[s] = bool(((k < ext_ns[s]) & (tk >= open_ns[s]) & (extreme[s] < lv)).any())
        lv, k, tk = own
        taken = np.sort(lv[(k <= open_ns[s]) & (tk >= open_ns[s]) & (extreme[s] < lv)])
        liq_equal[s] = bool(len(taken) > 1 and (np.diff(taken) <= _EQUAL_SHARE * avg[s]).any())
    out["liq_htf_swing"], out["liq_equal"] = liq_htf, liq_equal

    # The dealing range, in real prices.
    pd_values = np.full(n, np.nan)
    if ranges is not None:
        (lo_lv, lo_k, lo_tk), (hi_lv, hi_k, hi_tk) = ranges
        real = sign * extreme
        for s in range(n):
            low_ref = _last_untaken(lo_lv, lo_k, lo_tk, open_ns[s])
            high_ref = -_last_untaken(hi_lv, hi_k, hi_tk, open_ns[s])           # highs are stored oriented
            if np.isfinite(low_ref) and np.isfinite(high_ref) and high_ref > low_ref:
                pd_values[s] = (real[s] - low_ref) / (high_ref - low_ref)
    out["pd"] = pd_values
    out["pd_zone"] = np.array([pd_zone(side, v) for v in pd_values], dtype=object)
    out["pd_aligned"] = np.isin(out["pd_zone"], ["discount", "beyond"] if side == "low" else ["premium", "beyond"])

    # Time, at the extreme's minute.
    cal = calendar_columns(pd.DatetimeIndex(ext_ns).tz_localize("UTC"))
    minute = cal["ny_minute"].to_numpy().astype(int)
    out.update(ny_hour=minute // 60, session=_session(minute), killzone=cal["killzone"].to_numpy(),
               h4_index=cal["h4_index"].to_numpy(), weekday=cal["weekday"].to_numpy())

    # Anatomy, on the oriented bars.
    prev = np.maximum(i - 1, 0)
    rng_i = h[i] - l[i]
    with np.errstate(invalid="ignore", divide="ignore"):
        out["turtle_soup"] = (l[i] < l[prev]) & (c[i] > l[prev])
        out["wick_share"] = np.where(rng_i > 0, (np.minimum(o[i], c[i]) - l[i]) / rng_i, np.nan)
        out["displacement"] = np.abs(c[conf] - o[conf]) / avg
    out["closes_beyond"] = np.where(is_three, c[conf] > h[i], swings["engulf_full"].to_numpy(bool))
    out["own_fvg"] = np.where(is_three, l[conf] > h[prev], None)
    return pd.DataFrame(out, index=swings.index)[CONTEXT_COLUMNS]


def build_context(frame: InstrumentFrame, swings: pd.DataFrame, arrays: pd.DataFrame,
                  all_swings: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """The swing table (one timeframe or several) with the context columns. ``all_swings`` holds every
    timeframe's swings (default ``swings``): the next timeframe's swings are its levels and its dealing range."""
    all_swings = swings if all_swings is None else all_swings
    m1_t = frame.arrays["time"]
    views = {side: _Arrays(arrays, side) for side in ("low", "high")}
    parts = []
    for tf_value in swings["tf"].unique():
        tf = Timeframe(tf_value)
        nxt = NEXT_TF.get(tf)
        ranges = None
        if nxt is not None:
            rng = all_swings[all_swings["tf"] == nxt.value]
            ranges = (_swing_levels(rng, "low", m1_t, frame.arrays["low"]),
                      _swing_levels(rng, "high", m1_t, -frame.arrays["high"]))
        for side in ("low", "high"):
            group = swings[(swings["tf"] == tf_value) & (swings["side"] == side)]
            if len(group):
                parts.append(_side_context(frame, group, all_swings, views[side], tf, side, ranges))
    context = pd.concat(parts).reindex(swings.index) if parts else pd.DataFrame(columns=CONTEXT_COLUMNS)
    return pd.concat([swings, context], axis=1)
