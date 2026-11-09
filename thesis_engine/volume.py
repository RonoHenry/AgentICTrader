"""Volume Profile (thesis-engine Requirement 25; H-AO): where a closed period's tick volume traded, read as of a cut.

The volume is the broker's tick volume, a count of quote changes and not contracts traded. A profile is built from a
period's M1 bars alone: equal price bins from the period's low to its high, each bar's volume spread evenly over the
bins it traded. Nothing here reads a bar after the period it was asked for, so the machine sees only closed periods
(the last W1 or D1 candle closed by the order's time) and the leg up to the CISD's close.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from liquidity_engine.context.frame_state import Candles

__all__ = ["GATES", "Profile", "Profiles", "build", "passes"]

GATES = ("POC", "VA", "NEAR", "PATH")


@dataclass(frozen=True)
class Profile:
    low: float
    width: float                                   # one bin's height in price
    volume: np.ndarray                             # each bin's share of the tick volume, lowest bin first
    poc: float
    vah: float
    val: float

    def density(self, a: float, b: float) -> float:
        """The mean volume per bin between two prices over the whole profile's mean: under 1 is thin. Bins outside
        the profile count as empty."""
        lo, hi = min(a, b), max(a, b)
        if not hi > lo or not self.volume.mean() > 0:
            return float("inf")
        mids = self.low + (np.arange(len(self.volume)) + 0.5) * self.width
        inside = float(self.volume[(mids >= lo) & (mids <= hi)].sum())
        return inside / ((hi - lo) / self.width) / float(self.volume.mean())


def build(lows: np.ndarray, highs: np.ndarray, volumes: np.ndarray, bins: int, value: float = 0.70
          ) -> Optional[Profile]:
    """The profile of these bars; None when they have no range or no volume."""
    if not len(lows):
        return None
    lo, hi, total = float(lows.min()), float(highs.max()), float(volumes.sum())
    if not hi > lo or not total > 0:
        return None
    width = (hi - lo) / bins
    first = np.clip(((lows - lo) / width).astype(np.int64), 0, bins - 1)
    last = np.clip(((highs - lo) / width).astype(np.int64), 0, bins - 1)
    each = volumes / (last - first + 1)
    step = np.zeros(bins + 1)                      # each bar adds its share from its first bin to its last
    np.add.at(step, first, each)
    np.add.at(step, last + 1, -each)
    vol = np.maximum(np.cumsum(step)[:-1], 0.0)

    top = np.flatnonzero(np.isclose(vol, vol.max()))
    middle = (bins - 1) / 2
    p = int(top[np.lexsort((top, np.abs(top - middle)))[0]])      # nearest the range's middle, then the lower

    a = b = p                                      # the value area: the bins a..b
    held, target = float(vol[p]), value * float(vol.sum())
    while held < target and (a > 0 or b < bins - 1):
        up = float(vol[b + 1]) if b < bins - 1 else -1.0
        down = float(vol[a - 1]) if a > 0 else -1.0
        if up > down:
            b += 1
            held += up
        elif down > up:
            a -= 1
            held += down
        else:
            a, b, held = a - 1, b + 1, held + up + down
    return Profile(lo, width, vol, lo + (p + 0.5) * width, lo + (b + 1) * width, lo + a * width)


class Profiles:
    """One market's M1 volume, read as profiles of any period. Shared by every run on those bars."""

    def __init__(self, t: np.ndarray, lows: np.ndarray, highs: np.ndarray, volumes: np.ndarray) -> None:
        self.t, self.lows, self.highs, self.volumes = t, lows, highs, volumes
        self._built: Dict[tuple, Optional[Profile]] = {}

    def of(self, start: int, end: int, bins: int, value: float = 0.70) -> Optional[Profile]:
        """The profile of the M1 bars opening in [start, end) (UTC ns)."""
        key = (start, end, bins, value)
        if key not in self._built:
            i, j = np.searchsorted(self.t, [start, end], "left")
            self._built[key] = build(self.lows[i:j], self.highs[i:j], self.volumes[i:j], bins, value)
        return self._built[key]

    def previous(self, c: Candles, t: int, bins: int, value: float = 0.70) -> Optional[Profile]:
        """The profile of the last candle of ``c`` closed by ``t``."""
        k = int(np.searchsorted(c.end, t, "right")) - 1
        return self.of(int(c.t[k]), int(c.end[k]), bins, value) if k >= 0 else None

    def leg_poc(self, start: int, end: int, bins: int) -> Optional[float]:
        p = self.of(start, end, bins)
        return p.poc if p is not None else None


def passes(gate: str, p: Optional[Profile], bull: bool, entry: float, risk: float, extreme: float, adr: float,
           near_adr: float, rr: float) -> bool:
    """Whether a hand clears a gate (H-AO). With no profile for its period it doesn't."""
    if p is None:
        return False
    if gate == "POC":
        return entry <= p.poc if bull else entry >= p.poc
    if gate == "VA":
        return entry <= p.val if bull else entry >= p.vah
    if gate == "NEAR":
        return min(abs(extreme - x) for x in (p.poc, p.vah, p.val)) <= near_adr * adr
    if gate == "PATH":
        return p.density(entry, entry + rr * risk if bull else entry - rr * risk) < 1.0
    raise ValueError(f"unknown volume gate {gate!r}")
