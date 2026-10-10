"""The volatility profile: where each instrument makes its range (update 2026-10e).

Time works through volatility, and the sessions that carry the range differ by
instrument. This describes them from the M1 bars of a span of trading dates
(the exploration slice), per instrument:

- per H4 candle (17:00, 21:00, 01:00, 05:00, 09:00, 13:00 New York): its median
  range, and its median share of the day's range;
- per New York hour: the share of days whose high, and whose low, formed in it
  (the earliest bar on a tie);
- per weekday: the median day range, and the H4 candle that most often holds the
  day's high and its low, with that share;
- a data caveat: the share of days whose high or low formed on a bar whose spread
  was 5x typical or more. Prices are bid, and the bid dips when the spread widens
  at the 17:00 rollover, so those extremes are likely spread artefacts.

It is descriptive: no verdict, no ledger row (Req 21.3).

    profiles = [instrument_profile(frames[i], start, end) for i in instruments]
    text = render_profile(profiles, {"snapshot": ..., "slice": ..., "code_commit": ...})

Validates: Requirement 21.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from algo_research.frame import InstrumentFrame

__all__ = ["H4_NAMES", "SPREAD_BLOWOUT", "InstrumentProfile", "instrument_profile", "render_profile"]

H4_NAMES = {0: "17:00", 1: "21:00", 2: "01:00", 3: "05:00", 4: "09:00", 5: "13:00"}
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SPREAD_BLOWOUT = 5.0                                     # x the typical spread: a rollover-style blowout


@dataclass
class InstrumentProfile:
    instrument: str
    days: int
    h4: pd.DataFrame            # index h4_index 0-5: median_range, median_share
    hours: pd.DataFrame         # index New York hour 0-23: high_share, low_share
    weekdays: pd.DataFrame      # index Mon-Fri: days, median_range, high_h4, high_h4_share, low_h4, low_h4_share
    spread_highs: float = 0.0   # share of days whose high formed on a spread of SPREAD_BLOWOUT x typical or more
    spread_lows: float = 0.0    # the same for the lows: bid prices dip when the spread widens at the rollover


def instrument_profile(frame: InstrumentFrame, start: date, end: date) -> InstrumentProfile:
    """The profile of ``frame``'s trading dates in [start, end)."""
    m1 = frame.m1
    dates = pd.DatetimeIndex(m1["trading_date"])
    m1 = m1[(dates >= pd.Timestamp(start)) & (dates < pd.Timestamp(end))].reset_index(drop=True)
    if m1.empty:
        return InstrumentProfile(frame.instrument, 0, _empty_h4(), _empty_hours(), _empty_weekdays())

    by_day = m1.groupby("trading_date", sort=True)
    day_range = by_day["high"].max() - by_day["low"].min()
    by_h4 = m1.groupby(["trading_date", "h4_index"], sort=True)
    h4_range = (by_h4["high"].max() - by_h4["low"].min()).rename("range").reset_index()
    h4_range["share"] = h4_range["range"] / day_range.reindex(h4_range["trading_date"]).to_numpy()
    h4 = (h4_range.groupby("h4_index").agg(median_range=("range", "median"), median_share=("share", "median"))
          .reindex(range(6)))

    hour = (m1["ny_minute"].to_numpy(dtype=int) // 60)
    high_at, low_at = by_day["high"].idxmax().to_numpy(), by_day["low"].idxmin().to_numpy()   # the earliest bar
    days = len(day_range)
    hours = pd.DataFrame({
        "high_share": pd.Series(hour[high_at]).value_counts().reindex(range(24), fill_value=0) / days,
        "low_share": pd.Series(hour[low_at]).value_counts().reindex(range(24), fill_value=0) / days,
    })

    h4_index = m1["h4_index"].to_numpy(dtype=int)
    per_day = pd.DataFrame({"range": day_range.to_numpy(), "weekday": day_range.index.weekday,
                            "high_h4": h4_index[high_at], "low_h4": h4_index[low_at]})
    rows = {}
    for weekday, part in per_day.groupby("weekday", sort=True):
        high_h4, high_share = _mode(part["high_h4"])
        low_h4, low_share = _mode(part["low_h4"])
        rows[_WEEKDAYS[weekday]] = {"days": len(part), "median_range": float(part["range"].median()),
                                    "high_h4": H4_NAMES[high_h4], "high_h4_share": high_share,
                                    "low_h4": H4_NAMES[low_h4], "low_h4_share": low_share}
    weekdays = pd.DataFrame.from_dict(rows, orient="index")
    blown = m1["spread"].to_numpy(dtype=float) >= SPREAD_BLOWOUT * frame.typical_spread
    return InstrumentProfile(frame.instrument, days, h4, hours, weekdays,
                             spread_highs=float(blown[high_at].mean()), spread_lows=float(blown[low_at].mean()))


def _mode(values: pd.Series) -> tuple[int, float]:
    counts = values.value_counts().sort_index()
    top = int(counts.idxmax())                       # the earliest H4 on a tie
    return top, float(counts.max() / len(values))


def _empty_h4() -> pd.DataFrame:
    return pd.DataFrame({"median_range": np.nan, "median_share": np.nan}, index=range(6))


def _empty_hours() -> pd.DataFrame:
    return pd.DataFrame({"high_share": 0.0, "low_share": 0.0}, index=range(24))


def _empty_weekdays() -> pd.DataFrame:
    return pd.DataFrame(columns=["days", "median_range", "high_h4", "high_h4_share", "low_h4", "low_h4_share"])


# ── rendering ──────────────────────────────────────────────────────────────

def render_profile(profiles: Sequence[InstrumentProfile], inputs: Mapping[str, str]) -> str:
    lines = ["# Volatility profile", "",
             "Where each instrument makes its range, by H4 candle, by New York hour and by weekday "
             "(AlgoResearch update 2026-10e, Requirement 21.3). Descriptive only: no verdict, no ledger row. "
             "Times are New York; the trading day opens at 17:00.", ""]
    for p in profiles:
        lines += [f"## {p.instrument}", "", f"{p.days} trading dates.", ""]
        if p.spread_lows or p.spread_highs:
            lines += [f"**Data caveat:** {_pct(p.spread_lows)} of the days' lows and {_pct(p.spread_highs)} of their highs "
                      f"formed on a bar whose spread was {SPREAD_BLOWOUT:g}x typical or more. Prices are bid, and the bid "
                      "dips when the spread widens at the 17:00 rollover, so these are likely spread artefacts, "
                      "not real extremes.", ""]
        lines += ["### By H4 candle", "",
                  "| H4 candle | Median range | Median share of the day's range |", "|---|---|---|"]
        for index, row in p.h4.iterrows():
            lines.append(f"| {H4_NAMES[index]} | {_price(row['median_range'])} | {_pct(row['median_share'])} |")
        lines += ["", "### Hour of the day's high and low", "",
                  "Share of days whose high, and whose low, formed in each New York hour (hours with neither are left out).",
                  "", "| Hour | High | Low |", "|---|---|---|"]
        for hour, row in p.hours.iterrows():
            if row["high_share"] or row["low_share"]:
                lines.append(f"| {hour:02d}:00 | {_pct(row['high_share'])} | {_pct(row['low_share'])} |")
        lines += ["", "### By weekday", "",
                  "| Weekday | Days | Median day range | High most often in | Low most often in |", "|---|---|---|---|---|"]
        for weekday, row in p.weekdays.iterrows():
            lines.append(f"| {weekday} | {int(row['days'])} | {_price(row['median_range'])} | "
                         f"{row['high_h4']} ({_pct(row['high_h4_share'])}) | {row['low_h4']} ({_pct(row['low_h4_share'])}) |")
        lines.append("")
    lines += ["## Inputs", "", f"- Snapshot: {inputs.get('snapshot', '–')}", f"- Dates: {inputs.get('slice', '–')}",
              f"- Code commit: `{inputs.get('code_commit', '–')}`", ""]
    return "\n".join(lines)


def _price(value) -> str:
    return "–" if value is None or not np.isfinite(value) else f"{value:.5g}"


def _pct(value) -> str:
    return "–" if value is None or not np.isfinite(value) else f"{100 * value:.0f}%"
