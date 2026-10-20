"""The trader's "Fractal + POI" indicator, ported from Pine v6 for Noculus (algo-backtester Requirements 21–23).

    reader = FractalPOI(m1, "M15", FractalSettings(), "XAUUSD", partners={"DXY": dxy_m1, "EURUSD": eur_m1})
    view = reader.at(clock)                # what the indicator shows at the replay clock

The source is ``backend/FractalPOI.md``. It is ported in four parts:
- ``frames``: the Fractal modes and every candle boundary;
- ``model``: HTF candles, C1/C2 sweeps, CISD, IC-CISD, the C3 and C4 entry zones, SD projections, formation
  liquidity and SMT;
- ``liquidity``: the liquidity suite;
- ``imbalance``: the HTF fair value gaps.

**Reading.** The reader reads the chart's candles one by one, each once it has closed by the clock, and draws
what the indicator shows on its last bar (Requirement 22). Nothing it sends comes from a candle that closes
after the clock: ``at(t)`` is the same whether or not later data exists (Property 11).

**The clock's candle.** It counts as Pine's last bar for positions: the HTF candles are drawn ``offset`` candles
to its right, and lines that run "to now" end on it.

**Moving the clock.** Forward is incremental. Back restores the nearest checkpoint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from algo_research.fractal_poi.chart import Chart, Now
from algo_research.fractal_poi.frames import (MODES, PERIOD, bsl_auto, fractal_htf, fvg_auto, fvg_label, htf_name,
                                               in_seconds, ltf_name, valid_htf)
from algo_research.fractal_poi.imbalance import Imbalance
from algo_research.fractal_poi.liquidity import Liquidity
from algo_research.fractal_poi.model import Model, Partner
from algo_research.fractal_poi.settings import DRAW_ONLY, FractalSettings
from algo_research.replay.timeframes import DAY, aggregate, wall_seconds

__all__ = ["DRAW_ONLY", "MODES", "PARTNERS", "FractalPOI", "FractalSettings", "defaults", "partners_for",
           "warmup_days"]

#: SMT partners for the "Automatic" mode, from the focus triads (D33): the indicator's own list comes from the
#: fstarcapital AssetCorrelationUtils library, which isn't published with it. (name, inverse) pairs.
PARTNERS = {
    "EURUSD": (("GBPUSD", False), ("DXY", True)),
    "GBPUSD": (("EURUSD", False), ("DXY", True)),
    "DXY": (("EURUSD", True), ("GBPUSD", True)),
    "XAUUSD": (("DXY", True), ("EURUSD", False)),
    "US100": (("US500", False), ("US30", False)),
    "US500": (("US100", False), ("US30", False)),
    "US30": (("US100", False), ("US500", False)),
    "GER40": (("UK100", False), ("US500", False)),
    "UK100": (("GER40", False), ("US500", False)),
}
CHECKPOINT_EVERY = 250


def defaults() -> dict:
    """The indicator's inputs as the settings dialog needs them: the defaults, the Fractal modes and the drawing
    inputs (those that redraw without rereading)."""
    return {"settings": FractalSettings().to_dict(), "modes": list(MODES), "draw_only": sorted(DRAW_ONLY),
            "partners": {k: [list(x) for x in v] for k, v in PARTNERS.items()}}


def partners_for(symbol: str, s: FractalSettings, available) -> list[tuple[str, bool]]:
    """The SMT partners the settings name for ``symbol``, among the instruments ``available``."""
    if s.smt_mode == "Manual":
        chosen = [(s.smt_sym1, s.smt_sym1_inverse), (s.smt_sym2, s.smt_sym2_inverse)]
    else:
        chosen = list(PARTNERS.get(symbol.upper(), ()))
    return [(name.upper(), inverse) for name, inverse in chosen if name and name.upper() in set(available)
            and name.upper() != symbol.upper()]


def warmup_days(tf: str, s: FractalSettings) -> int:
    """How much history the reader needs before the first candle it is asked about: enough HTF candles for
    the setups, levels and gaps it keeps, and the previous week (and month, when shown). At most 120 days."""
    def periods(htf: str, n: int) -> float:
        sec = in_seconds(htf) or 0
        return n * sec / DAY
    htf = fractal_htf(s.fractal_mode, tf, s.custom_htf)
    need = [3.0, periods(htf if valid_htf(htf, tf) else "1D", s.max_display + s.sweep_history + 6),
            periods(fvg_auto(tf) if s.fvg_auto_mode else s.fvg_manual_htf, 60)]
    if s.lq_show_pw:
        need.append(15)
    if s.lq_show_pm:
        need.append(65)
    for on, ltf in ((s.lq_show_htf1, bsl_auto(tf) if s.lq_htf1_mode == "Auto" else s.lq_htf1_manual),
                    (s.lq_show_htf2, s.lq_htf2_manual), (s.lq_show_htf3, s.lq_htf3_manual)):
        if on:
            need.append(periods(ltf, 40))
    return int(min(120, np.ceil(max(need)) + 1))


def _arrays(m1: pd.DataFrame) -> tuple:
    m1 = m1.sort_values("time", kind="stable")
    return (wall_seconds(pd.to_datetime(m1["time"], utc=True)),
            *(m1[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close")))


class FractalPOI:
    """The indicator over one instrument and one chart timeframe, with one set of computing inputs."""

    def __init__(self, m1: pd.DataFrame, tf: str, settings: FractalSettings, symbol: str,
                 partners: Optional[dict[str, tuple[pd.DataFrame, bool]]] = None) -> None:
        if tf not in PERIOD:
            raise ValueError(f"tf: one of {', '.join(PERIOD)}")
        self.tf, self.s, self.symbol = tf, settings, symbol.upper()
        self.chart = Chart(*_arrays(m1), tf)
        self.partner_names = []
        aligned = []
        for name, (frame, inverse) in (partners or {}).items():
            aligned.append(Partner(name, *self._align(frame), inverse))
            self.partner_names.append(name)
        self.events: list[dict] = []
        self.model = Model(self.chart, settings, self.symbol, tuple(aligned), self.events)
        self.liquidity = Liquidity(self.chart, settings)
        self.imbalance = Imbalance(self.chart, settings)
        self.pos = -1
        self._checkpoints = {-1: self._state()}

    def _align(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """A partner's candles of this chart's timeframe, on this chart's candles: the one opening with it, else
        the last one before it (Pine's gaps_off). None open after it, so none closes after it."""
        wall, o, h, l, c = _arrays(frame)
        bars = aggregate(wall, o, h, l, c, self.tf)
        times = bars["time"].to_numpy(dtype=np.int64)
        k = np.searchsorted(times, self.chart.time, side="right") - 1
        ok = k >= 0
        high, low = np.full(self.chart.n, np.nan), np.full(self.chart.n, np.nan)
        high[ok] = bars["high"].to_numpy(dtype=float)[k[ok]]
        low[ok] = bars["low"].to_numpy(dtype=float)[k[ok]]
        return high, low

    # ── stepping ─────────────────────────────────────────────────────────────
    def _state(self) -> dict:
        return {"model": self.model.state(), "liquidity": self.liquidity.state(), "imbalance": self.imbalance.state(),
                "events": len(self.events)}

    def _restore(self, pos: int) -> None:
        state = self._checkpoints[pos]
        self.model.restore(state["model"])
        self.liquidity.restore(state["liquidity"])
        self.imbalance.restore(state["imbalance"])
        del self.events[state["events"]:]
        self.pos = pos

    def step_to(self, target: int) -> None:
        """Read candles up to ``target`` (an index; -1 is none read)."""
        if target < self.pos:
            self._restore(max(p for p in self._checkpoints if p <= target))
        while self.pos < target:
            self.pos += 1
            i = self.pos
            self.liquidity.step(i)
            self.imbalance.step(i)
            self.model.step(i)
            if i % CHECKPOINT_EVERY == 0:
                self._checkpoints[i] = self._state()

    # ── the view at the clock ────────────────────────────────────────────────
    def at(self, clock: int, draw: Optional[FractalSettings] = None) -> dict:
        """What the indicator shows at ``clock`` (wall seconds), drawn with ``draw``'s drawing inputs (its
        computing inputs must be this reader's)."""
        d = draw or self.s
        if d.compute_key() != self.s.compute_key():
            raise ValueError("draw: the drawing inputs may change, not the computing ones")
        clock = int(clock)
        self.step_to(self.chart.closed_by(clock))
        now = self.chart.now(clock)
        items: list[dict] = []
        if now is not None and self.pos >= 0:
            if now.idx < self.pos:            # the clock's candle can't be one read before the last closed one
                now = Now(self.pos, int(self.chart.time[self.pos]), int(self.chart.end[self.pos]), clock)
            items = (self.liquidity.draw(self.pos, now, d) + self.imbalance.draw(self.pos, now, d)
                     + self.model.draw(self.pos, now, d))
        forming = now is not None and now.end > clock
        return {"tf": self.tf, "clock": clock, "read_to": int(self.chart.end[self.pos]) if self.pos >= 0 else None,
                "refresh_at": now.end if forming else clock + 60, "items": items,
                "events": self._events(clock, d), "dashboard": self.dashboard(now, d)}

    def _events(self, clock: int, d: FractalSettings) -> list[dict]:
        if not d.events_show:
            return []
        out = []
        for e in self.events:
            if e["t"] > clock:
                continue
            bull = e["dir"] == "bull"
            if not (d.bias == "Neutral" or (d.bias == "Bullish") == bull):
                continue
            if (e["kind"] == "ic" and not d.ic_cisd_show) or (e["kind"] == "smt" and not d.smt_show):
                continue
            out.append(e)
        return out

    def dashboard(self, now: Optional[Now], d: FractalSettings) -> dict:
        htf = self.model.htf
        valid = self.model.valid
        out = {"asset": self.symbol, "ltf": ltf_name(self.tf), "htf1": htf_name(htf) if htf else "—",
               "htf2": htf_name(self.model.htf2) if d.htf2_show else "off", "bias": d.bias, "valid": valid,
               "fvg": fvg_label(self.imbalance.htf), "smt": self.partner_names,
               "date": datetime.fromtimestamp(now.time, timezone.utc).strftime("%d %b %Y") if now else None,
               "remaining": self.model.remaining(now) if (now and valid) else None,
               "htf_end": self.model.htf_end(now) if (now and valid) else None}
        if not valid:
            out["warning"] = (f"HTF1 ({out['htf1']}) is invalid for the chart's timeframe ({out['ltf']}): "
                              "check the Fractal setting")
        return out
