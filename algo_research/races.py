"""Races: does price reach the target before the stop, priced like the backtester?

A race is a hypothetical MARKET order at t with a stop, a target and a time
limit, run on the M1 path with the rules of the shared FillModel
(agent/brokers/fill_model.py; algo-backtester Requirement 4), so a research
edge survives being backtested (Requirement 7). Property 5 checks it against
stepping FillModel itself.

Rules:
1. The entry bar is the first M1 bar opening at or after t. LONG fills at its
   ask open (open + spread), SHORT at its bid open. When that price is already
   beyond the stop or the target, or no bar opens before the limit, the race
   is REJECTED: counted and excluded, as the broker rejects invalid stops.
2. From the entry bar to the last bar opening before the limit, the stop and
   the target trigger on the closing side: the bid for LONG, the ask for SHORT.
3. When one bar reaches both, the stop wins and the race is ``ambiguous``.
4. A bar opening beyond the stop exits at its open (a gap); stop exits are
   worsened by the spec's stop slippage; targets exit at the target.
5. With neither hit, the race is a TIMEOUT, exited at the last bar's close on
   the closing side, at that bar's close time.

Prices and R, as the backtester's (task 201):
- R = |fill - stop| on the executed entry;
- gross R on bid prices (the bid at the fill and at the exit), net R on
  executed prices, less commission converted to R per lot (commission and
  risk both scale with lots, so no sizing is needed). No swap (AR-D6);
- MFE and MAE: the closing-side excursions from the fill, in R.

For the baselines, each race also carries:
- ``p_coin``: a driftless path's chance of reaching the target first from the
  closing-side price at entry, (price - stop) / (target - stop) for LONG,
  mirrored for SHORT;
- ``score``: 1 at the target, 0 at the stop, and at a TIMEOUT the same
  chance from its exit price. Under no drift its expectation is ``p_coin``
  (Property 6), so a race cut short by its time limit neither wins nor loses
  by fiat; ``win_rate`` is the mean score.

Implementation: one NumPy slice per race and ``argmax`` on the hit arrays.

Validates: Requirements 7.1-7.4 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from agent.instruments import InstrumentSpec, commission_per_side, money_per_price_unit
from algo_research.frame import InstrumentFrame

__all__ = ["OUTCOMES", "RACE_COLUMNS", "RaceCosts", "run_races"]

OUTCOMES = ("TARGET", "STOP", "TIMEOUT", "REJECTED")
RACE_COLUMNS = ("t", "direction", "entry_time", "entry", "entry_bid", "stop", "target", "outcome", "exit_time",
                "exit", "exit_bid", "gross_r", "net_r", "commission_r", "mfe_r", "mae_r", "ambiguous",
                "holding_minutes", "p_coin", "score")

_MINUTE = 60 * 1_000_000_000
_NAT = np.iinfo(np.int64).min


@dataclass(frozen=True)
class RaceCosts:
    """What a race pays beyond the spread: stop slippage (price units) and
    commission in R, from the fill, the exit and 1R in price units."""
    stop_slippage: float
    commission_r: Optional[Callable[[float, float, float], float]] = None

    @classmethod
    def from_spec(cls, spec: InstrumentSpec, account_ccy: str) -> RaceCosts:
        def commission_r(fill: float, exit_price: float, risk: float) -> float:
            paid = (commission_per_side(spec, 1.0, fill, None, account_ccy)
                    + commission_per_side(spec, 1.0, exit_price, None, account_ccy))
            return paid / (risk * money_per_price_unit(spec, fill, None, account_ccy))

        no_commission = spec.commission.value == 0
        return cls(spec.stop_slippage, None if no_commission else commission_r)


def run_races(frame: InstrumentFrame, orders: pd.DataFrame, costs: Optional[RaceCosts] = None) -> pd.DataFrame:
    """One result row per order (columns t, direction, stop, target, limit), same index."""
    costs = costs or RaceCosts(frame.stop_slippage)
    a = frame.arrays
    mt, o, h, l, c, sp = a["time"], a["open"], a["high"], a["low"], a["close"], a["spread"]
    starts = np.searchsorted(mt, pd.DatetimeIndex(orders["t"]).as_unit("ns").asi8, "left")
    ends = np.searchsorted(mt, pd.DatetimeIndex(orders["limit"]).as_unit("ns").asi8, "left")
    rows = [_race(mt, o, h, l, c, sp, int(i0), int(end), direction, float(stop), float(target), costs)
            for i0, end, direction, stop, target in zip(starts, ends, orders["direction"], orders["stop"],
                                                         orders["target"])]
    out = pd.DataFrame(rows, index=orders.index, columns=RACE_COLUMNS[2:])
    out.insert(0, "direction", orders["direction"].to_numpy())
    out.insert(0, "t", pd.DatetimeIndex(orders["t"]))
    for name in ("entry_time", "exit_time"):
        out[name] = pd.DatetimeIndex(out[name].to_numpy(dtype=np.int64).astype("datetime64[ns]")).tz_localize("UTC")
    out["ambiguous"] = out["ambiguous"].astype(bool)
    return out[list(RACE_COLUMNS)]


def _rejected(stop: float, target: float, entry_time: int = _NAT) -> tuple:
    nan = float("nan")
    return (entry_time, nan, nan, stop, target, "REJECTED", _NAT, nan, nan, nan, nan, nan, nan, nan, False, nan,
            nan, nan)


def _race(mt, o, h, l, c, sp, i0: int, end: int, direction: str, stop: float, target: float,
          costs: RaceCosts) -> tuple:
    if i0 >= end:
        return _rejected(stop, target)                       # no bar opens before the limit
    long_ = direction == "LONG"
    sign = 1.0 if long_ else -1.0
    bid0, spread0 = o[i0], sp[i0]
    fill = bid0 + spread0 if long_ else bid0
    if (fill <= stop or fill >= target) if long_ else (fill >= stop or fill <= target):
        return _rejected(stop, target, mt[i0])
    closing0 = bid0 if long_ else bid0 + spread0              # where the position would close right now

    window = slice(i0, end)
    if long_:
        adverse, favourable = l[window], h[window]
        stop_hit, target_hit = adverse <= stop, favourable >= target
    else:
        adverse, favourable = h[window] + sp[window], l[window] + sp[window]
        stop_hit, target_hit = adverse >= stop, favourable <= target
    hits = stop_hit | target_hit
    pick_adverse, pick_favourable = (min, max) if long_ else (max, min)

    if hits.any():
        j = int(np.argmax(hits))
        bar = i0 + j
        before_adverse = adverse[:j]
        before_favourable = favourable[:j]
        if stop_hit[j]:
            outcome, ambiguous = "STOP", bool(target_hit[j])
            closing_open = o[bar] if long_ else o[bar] + sp[bar]
            gapped = closing_open < stop if long_ else closing_open > stop
            market = closing_open if gapped else stop
            exit_price = market - costs.stop_slippage if long_ else market + costs.stop_slippage
            exit_bid = market if long_ else market - sp[bar]
            mae = pick_adverse(closing0, market, *([before_adverse.min() if long_ else before_adverse.max()]
                                                   if j else []))
            mfe = pick_favourable(closing0, favourable[j], *([before_favourable.max() if long_
                                                              else before_favourable.min()] if j else []))
            score = 0.0
        else:
            outcome, ambiguous = "TARGET", False
            exit_price = target
            exit_bid = target if long_ else target - sp[bar]
            mae = pick_adverse(closing0, adverse[j], *([before_adverse.min() if long_ else before_adverse.max()]
                                                       if j else []))
            mfe = pick_favourable(closing0, target, *([before_favourable.max() if long_
                                                       else before_favourable.min()] if j else []))
            score = 1.0
        exit_time = mt[bar]
    else:
        outcome, ambiguous = "TIMEOUT", False
        last = end - 1
        exit_bid = c[last]
        exit_price = c[last] if long_ else c[last] + sp[last]
        mae = pick_adverse(closing0, adverse.min() if long_ else adverse.max())
        mfe = pick_favourable(closing0, favourable.max() if long_ else favourable.min())
        exit_time = mt[last] + _MINUTE
        score = min(max(_coin(long_, exit_price if not long_ else exit_bid, stop, target), 0.0), 1.0)

    risk = abs(fill - stop)
    commission = costs.commission_r(fill, exit_price, risk) if costs.commission_r else 0.0
    return (
        mt[i0], fill, bid0, stop, target, outcome, exit_time, exit_price, exit_bid,
        sign * (exit_bid - bid0) / risk,                      # gross: bid to bid
        sign * (exit_price - fill) / risk - commission,       # net: executed prices, less commission
        commission,
        sign * (mfe - fill) / risk, sign * (mae - fill) / risk,
        ambiguous, (exit_time - mt[i0]) / _MINUTE,
        _coin(long_, closing0, stop, target), score,
    )


def _coin(long_: bool, closing: float, stop: float, target: float) -> float:
    """A driftless path's chance of reaching the target before the stop, from ``closing``."""
    return (closing - stop) / (target - stop) if long_ else (stop - closing) / (stop - target)
