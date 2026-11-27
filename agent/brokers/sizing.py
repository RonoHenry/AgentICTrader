"""The sizing rule every broker shares (live-execution Requirements 1, 2, 7).

SimBroker (the backtest) and MT5BrokerAdapter (live) size a risk-based order
with these functions, so a demo order's lots are the ones the backtest traded:

    lots = lots_for_risk(budget, risk_per_lot, volume_min, volume_step, volume_max)
    part = split_lots(lots, 1 / 3, volume_min, volume_step)    # 0.0: runs unmanaged (D44)
    if stop_overrun(abs(entry - stop), spread, slippage) > 0.5: refuse STOP_TOO_TIGHT

``risk_per_lot`` is the money one lot loses from the entry to the stop. Lots
round DOWN to the step and are capped at the maximum, so a trade never risks
more than its budget, except at the minimum volume, which is allowed up to
``tolerance`` over (10% by default) and refused beyond it.

Validates: Requirements 1.1-1.3, 2.1, 7.1 (.kiro/specs/live-execution/requirements.md)
"""
from __future__ import annotations

import math
from decimal import Decimal

__all__ = ["SizingError", "lots_for_risk", "round_down", "split_lots", "stop_overrun"]


class SizingError(Exception):
    """An order the sizing rule refuses. ``reason`` is the code the journal records."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def round_down(value: float, step: float) -> float:
    """``value`` rounded down to a multiple of ``step``, at the step's precision."""
    steps = math.floor(value / step + 1e-9)   # 0.3 / 0.1 is 2.9999999999999996
    exponent = Decimal(repr(step)).normalize().as_tuple().exponent   # a finite step's is an int
    return round(steps * step, max(0, -exponent) if isinstance(exponent, int) else 0)


def lots_for_risk(budget: float, risk_per_lot: float, volume_min: float, volume_step: float, volume_max: float,
                  tolerance: float = 0.10) -> float:
    """The lots whose loss at the stop is the budget: rounded down to the step, capped at the maximum. Under the
    minimum, the minimum if it risks at most ``tolerance`` over the budget; otherwise MIN_VOLUME_OVER_RISK."""
    lots = min(round_down(budget / risk_per_lot, volume_step), volume_max)
    if lots >= volume_min:
        return lots
    if volume_min * risk_per_lot > budget * (1 + tolerance):
        raise SizingError(
            "MIN_VOLUME_OVER_RISK",
            f"{volume_min} lots risk {volume_min * risk_per_lot:.2f}, over the {budget:.2f} budget + {tolerance:.0%}",
        )
    return volume_min


def split_lots(lots: float, fraction: float, volume_min: float, volume_step: float) -> float:
    """The partial's lots: ``fraction`` of ``lots`` rounded down to the step, or 0.0 when the part or the rest
    would be under the minimum volume, and the trade runs unmanaged (algo-backtester D44)."""
    if fraction <= 0:
        return 0.0
    part = round_down(lots * fraction, volume_step)
    if part < volume_min or lots - part < volume_min - 1e-9:
        return 0.0
    return part


def stop_overrun(stop_distance: float, spread: float, slippage: float) -> float:
    """What the spread and the stop's slippage add to a stop-out, as a share of the stop distance: at 0.5 a
    stop-out loses up to 1.5 times what the trade was sized to risk."""
    if stop_distance <= 0:
        return math.inf
    return (spread + slippage) / stop_distance
