"""Delivery (algomind-dis Requirement 7, §7): the delivery state read from a sequence, never from one event.

A bullish sequence (a bearish one is the mirror):
1. **the sweep:** a candle trades under the latest known swing low (``arrays._swept``);
2. **the CISD:** reader v0's rule (``algo_research.sequence.cisd``): the run of down-closing candles that delivered
   the sweep, its first open the level, and the first later close above it;
3. **the displacement:** a bullish displacement candle (``ranges.displacements``) from the sweep to the CISD.

The state, in this order:
- **TRANSITIONAL:** the latest sweep with a displacement away from it but no CISD yet, against the ongoing delivery
  or with none;
- **CONSOLIDATION:** ``algo_research.phases`` labels the last candle consolidation;
- **BULLISH_DELIVERY:** the latest complete sequence is bullish and no candle has closed under its sweep's low since;
- **UNCONFIRMED:** none of these.

Every part reads only candles up to its own; the replay computes the sequences and the phase labels once on the
full frame (``seqs``, ``labels``) and each close reads the ones complete by then.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from algo_research import sequence as seq
from algo_research.phases import CONSOLIDATION, label_phases
from algomind_dis.analyzers.arrays import _swept
from algomind_dis.analyzers.ranges import displacements
from algomind_dis.records import DeliveryState
from algomind_dis.settings import V1, Settings
from liquidity_engine.context.frame_state import Candles

__all__ = ["Seq", "delivery", "sequences"]


@dataclass(frozen=True)
class Seq:
    side: str                    # BULLISH after a sell-side sweep
    sweep: int                   # the sweeping candle
    level: float                 # the CISD level: the open of the run that delivered the sweep
    confirm: int                 # the candle closing beyond the level, or -1 by the frame's end
    displaced: bool              # a displacement of its side from the sweep to the confirm
    extreme: float               # the sweep's low (high): a close beyond it ends the delivery


def _frame(c: Candles, flip: bool) -> pd.DataFrame:
    s = -1.0 if flip else 1.0
    o, h, l, cl = (s * c.o, s * c.l, s * c.h, s * c.c) if flip else (c.o, c.h, c.l, c.c)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": cl, "t_close": c.end})


def sequences(c: Candles, s: Settings = V1) -> list[Seq]:
    """Every sweep's sequence on the frame, both sides, in sweep order."""
    if len(c) < 3:
        return []
    under, over = _swept(c)
    disp = displacements(c, s)
    until = int(c.end[-1])
    out = []
    for side, swept, flip, sign in (("BULLISH", under, False, 1), ("BEARISH", over, True, -1)):
        frame = _frame(c, flip)
        for k in np.flatnonzero(swept):
            x = seq.cisd(frame, int(k), until)
            if x is None:
                continue
            j = int(x["confirm"])
            displaced = j >= 0 and bool((disp[k:j + 1] == sign).any())
            extreme = float(c.l[x["start"]:k + 1].min()) if sign > 0 else float(c.h[x["start"]:k + 1].max())
            out.append(Seq(side, int(k), sign * float(x["level"]), j, displaced, extreme))
    return sorted(out, key=lambda q: (q.sweep, q.side))


def _p(x: float) -> str:
    return f"{x:.6g}"


def delivery(c: Candles, s: Settings = V1, seqs: Optional[Sequence[Seq]] = None,
             labels: Optional[np.ndarray] = None) -> DeliveryState:
    n = len(c)
    if n == 0:
        return DeliveryState(c.tf, "UNCONFIRMED", None, ("no closed candle",))
    seqs = sequences(c, s) if seqs is None else seqs
    seqs = [q for q in seqs if q.sweep < n]
    done = [q for q in seqs if 0 <= q.confirm < n and q.displaced]
    latest = max(done, key=lambda q: (q.confirm, q.sweep)) if done else None
    ongoing = None
    if latest is not None:
        after = c.c[latest.confirm + 1:n]
        beyond = (after < latest.extreme) if latest.side == "BULLISH" else (after > latest.extreme)
        if not beyond.any():
            ongoing = latest
    disp = displacements(c, s)
    pending = [q for q in seqs if not (0 <= q.confirm < n)
               and (latest is None or q.sweep > latest.confirm)
               and bool((disp[q.sweep:n] == (1 if q.side == "BULLISH" else -1)).any())]
    word = {"BULLISH": ("sell", "low", "above"), "BEARISH": ("buy", "high", "below")}
    if pending and (ongoing is None or pending[-1].side != ongoing.side):
        q = pending[-1]
        side, extreme, beyond = word[q.side]
        return DeliveryState(c.tf, "TRANSITIONAL", int(c.end[q.sweep]),
                             (f"{side}-side swept to {_p(q.extreme)} and a {q.side.lower()} displacement",
                              f"no close {beyond} {_p(q.level)} (the CISD) yet"))
    labels = label_phases(c.o, c.h, c.l, c.c) if labels is None else labels
    if n <= len(labels) and labels[n - 1] == CONSOLIDATION:
        return DeliveryState(c.tf, "CONSOLIDATION", int(c.end[n - 1]), ("a tight box (algo_research.phases)",))
    if ongoing is not None:
        side, extreme, beyond = word[ongoing.side]
        return DeliveryState(c.tf, f"{ongoing.side}_DELIVERY", int(c.end[ongoing.confirm]),
                             (f"{side}-side swept to {_p(ongoing.extreme)}",
                              f"a {ongoing.side.lower()} displacement and a close {beyond} {_p(ongoing.level)} "
                              f"(the CISD)",
                              f"held while no close is beyond {_p(ongoing.extreme)}"))
    return DeliveryState(c.tf, "UNCONFIRMED", None, ("no complete sweep, displacement and CISD in force",))
