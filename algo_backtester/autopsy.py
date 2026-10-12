"""The trade autopsy: a run's trades read against how their candles formed.

A backtest's summary says *that* a run fails. The autopsy says where, in the
trader's terms (.kiro/specs/market-narrative, Requirements 3-4). Every filled
trade is labelled with the narrative of the candles it filled in (W1, D1 and H4
by default), and the run's net R is split by failure mode, judged on the bias
frame's candle (D1):

- ``WITH_ON_TIME``: with the candle, filled after its false move, up to its
  expansion extreme;
- ``WITH_EARLY``: with it, filled before or at the false-move extreme;
- ``WITH_LATE``: with it, filled after the expansion extreme;
- ``WITH_INVERTED``: with it, on a candle whose expansion extreme came first;
- ``AGAINST_EXPANSION``: against it, filled while it expanded;
- ``AGAINST_OTHER``: against it, any other time;
- ``UNKNOWN``: a FLAT, incomplete or missing candle.

Per trade it also records whether an early fill was stopped by the false
move, whether the target lay beyond the expansion extreme, which side of the
open the setup's raid and the fill were on, and one as-of column: the shape
of the candle so far, from bars closed before the fill.

The run directory is the only input (journal.csv, context.json, candles.json),
so the autopsy works on old runs without the candle store. Its labels are
hindsight: they diagnose, never decide (Requirement 5).

    python -m algo_backtester autopsy data/backtests/<run_id>

Validates: Requirements 3.1-3.6, 5.2 (.kiro/specs/market-narrative/requirements.md)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from algo_research.narrative import NarrativeConfig, apply_price_basis, fill_phase, narrate
from algo_research.narrative.candles import _MINUTES
from algo_research.stats import Bootstrap, seed_from, series_table
from liquidity_engine.models import Timeframe
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["AUTOPSY_COLUMNS", "FAILURE_MODES", "AutopsyError", "RunInputs", "autopsy_table", "load_run",
           "run_seed", "split"]

FAILURE_MODES = ("WITH_ON_TIME", "WITH_EARLY", "WITH_LATE", "WITH_INVERTED",
                 "AGAINST_EXPANSION", "AGAINST_OTHER", "UNKNOWN")
_JOURNAL = ("t", "instrument", "setup_id", "direction", "entry", "stop", "target", "fill", "filled_at",
            "exit_reason", "net_r", "mfe_r")
_BIAS = ("bias_start", "phase", "stopped_by_false_move", "target_beyond_expansion", "raid_beyond_open",
         "raid_in_candle", "raid_tf", "raid_source", "fill_side", "asof_shape", "mode")
_RUN_FILES = ("journal.csv", "context.json", "candles.json")
_NY = "America/New_York"
_SERVER_SHIFT = timedelta(hours=7)          # the ny_close server clock: New York wall time + 7 h
_CALENDAR = StrategyCalendar()


def autopsy_columns(frames=(Timeframe.W1, Timeframe.D1, Timeframe.H4)) -> tuple[str, ...]:
    per_frame = tuple(c for tf in frames for c in (f"{tf.value}_dir", f"{tf.value}_with"))
    return (*_JOURNAL, "trading_date", "ny_hour", *per_frame, *_BIAS)


AUTOPSY_COLUMNS = autopsy_columns()


class AutopsyError(Exception):
    """A run directory the autopsy can't read, or candles too coarse for a frame."""


@dataclass(frozen=True)
class RunInputs:
    run_id: str
    journal: pd.DataFrame               # filled trades closed by stop, target or time
    open_at_end: int                    # trades still open when the run ended (left out)
    contexts: dict[str, dict]           # setup_id -> the order intent's recorded context
    bar_tf: Timeframe
    bars: dict[str, pd.DataFrame]       # instrument -> the run's entry-timeframe candles


def load_run(run_dir: Path) -> RunInputs:
    run_dir = Path(run_dir)
    missing = [name for name in _RUN_FILES if not (run_dir / name).is_file()]
    if missing:
        raise AutopsyError(f"{run_dir} is not a run directory: missing {', '.join(missing)}")
    journal = pd.read_csv(run_dir / "journal.csv", dtype={"setup_id": str}, keep_default_na=True)
    for name in _JOURNAL:
        if name not in journal:
            journal[name] = np.nan
    filled = journal[journal["filled_at"].notna()]
    open_at_end = int((filled["exit_reason"] == "OPEN_AT_END").sum())
    closed = filled[filled["closed_at"].notna() & (filled["exit_reason"] != "OPEN_AT_END")]
    contexts = {c["setup_id"]: c["context"]
                for c in json.loads((run_dir / "context.json").read_text(encoding="utf-8")) if c.get("setup_id")}
    candles = json.loads((run_dir / "candles.json").read_text(encoding="utf-8"))
    bars = {}
    for instrument, rows in sorted(candles["instruments"].items()):
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        bars[instrument] = df
    return RunInputs(run_id=run_dir.name, journal=closed.reset_index(drop=True), open_at_end=open_at_end,
                     contexts=contexts, bar_tf=Timeframe(candles["timeframe"]), bars=bars)


def run_seed(run_id: str) -> int:
    """The split's bootstrap seed, from the run id."""
    return seed_from(hashlib.sha256(run_id.encode("utf-8")).hexdigest())


# ── per-trade labels ────────────────────────────────────────────────────────

def _with(direction: str, candle_dir: str) -> Optional[bool]:
    if candle_dir not in ("UP", "DOWN"):
        return None
    return (direction == "LONG") == (candle_dir == "UP")


def _asof_shape(bars: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, step_end: pd.Series,
                filled: pd.Timestamp, long: bool) -> str:
    """The candle's shape from its bars closed by the fill: UP when its low so far
    came before its high and the last close is above the open; DOWN mirrored."""
    seen = bars[(bars["time"] >= start) & (bars["time"] < end) & (step_end <= filled)]
    if seen.empty:
        return "UNFORMED"
    t_low = seen["time"].iloc[int(np.argmin(seen["low"].to_numpy()))]
    t_high = seen["time"].iloc[int(np.argmax(seen["high"].to_numpy()))]
    first_open, last_close = seen["open"].iloc[0], seen["close"].iloc[-1]
    if t_low < t_high and last_close > first_open:
        shape = "UP"
    elif t_high < t_low and last_close < first_open:
        shape = "DOWN"
    else:
        return "UNFORMED"
    return "WITH_SHAPE" if (shape == "UP") == long else "FADES_SHAPE"


def _mode(with_bias: Optional[bool], phase: str) -> str:
    if phase == "UNKNOWN" or with_bias is None:
        return "UNKNOWN"
    if with_bias:
        return {"BEFORE_FALSE_EXTREME": "WITH_EARLY", "AT_FALSE_EXTREME": "WITH_EARLY",
                "IN_EXPANSION": "WITH_ON_TIME", "AFTER_EXPANSION": "WITH_LATE",
                "INVERTED": "WITH_INVERTED"}[phase]
    return "AGAINST_EXPANSION" if phase == "IN_EXPANSION" else "AGAINST_OTHER"


def _beyond(price: float, reference: float, long: bool) -> bool:
    """Below the reference for a long, above it for a short."""
    return price < reference if long else price > reference


def autopsy_table(inputs: RunInputs, cfg: NarrativeConfig) -> pd.DataFrame:
    """One row per filled, closed trade (``AUTOPSY_COLUMNS`` for ``cfg.frames``)."""
    for tf in cfg.frames:
        if _MINUTES[inputs.bar_tf] >= _MINUTES[tf]:
            raise AutopsyError(f"the run's {inputs.bar_tf.value} candles are not finer than the frame {tf.value}")
    columns = autopsy_columns(cfg.frames)
    priced, narratives, bar_ends = {}, {}, {}
    for instrument, bars in inputs.bars.items():
        priced[instrument] = apply_price_basis(bars, instrument, cfg.price_basis)
        narratives[instrument] = {tf: narrate(priced[instrument], inputs.bar_tf, tf, _CALENDAR).set_index("start")
                                  for tf in cfg.frames}
        bar_ends[instrument] = pd.Series([pd.Timestamp(_CALENDAR.period_end(t.to_pydatetime(), inputs.bar_tf))
                                          for t in priced[instrument]["time"]], index=priced[instrument].index)

    rows = []
    for trade in inputs.journal.itertuples(index=False):
        filled = pd.Timestamp(trade.filled_at).tz_convert("UTC")
        long = trade.direction == "LONG"
        d1_start = pd.Timestamp(_CALENDAR.period_start(filled.to_pydatetime(), Timeframe.D1))
        row: dict[str, Any] = {name: getattr(trade, name) for name in _JOURNAL}
        row["trading_date"] = (d1_start.tz_convert(_NY).tz_localize(None) + _SERVER_SHIFT).date().isoformat()
        row["ny_hour"] = filled.tz_convert(_NY).hour
        candles: dict[Timeframe, Optional[pd.Series]] = {}
        for tf in cfg.frames:
            start = pd.Timestamp(_CALENDAR.period_start(filled.to_pydatetime(), tf))
            table = narratives.get(trade.instrument, {}).get(tf)
            candle = table.loc[start] if table is not None and start in table.index else None
            if candle is not None and not bool(candle["complete"]):
                candle = None
            candles[tf] = candle if candle is None else candle.copy().rename(start)
            direction = "UNKNOWN" if candle is None else candle["direction"]
            row[f"{tf.value}_dir"], row[f"{tf.value}_with"] = direction, _with(trade.direction, direction)

        bias = candles[cfg.bias_frame]
        bias_start = pd.Timestamp(_CALENDAR.period_start(filled.to_pydatetime(), cfg.bias_frame))
        bias_end = pd.Timestamp(_CALENDAR.period_end(filled.to_pydatetime(), cfg.bias_frame))
        fill_bar = pd.Timestamp(_CALENDAR.period_start(filled.to_pydatetime(), inputs.bar_tf))
        phase = fill_phase(None if bias is None else {**bias.to_dict(), "complete": True}, fill_bar)
        with_bias = row[f"{cfg.bias_frame.value}_with"]
        row.update({"bias_start": bias_start.isoformat(), "phase": phase,
                    "stopped_by_false_move": None, "target_beyond_expansion": None,
                    "raid_beyond_open": None, "raid_in_candle": None, "raid_tf": None, "raid_source": None,
                    "fill_side": None})
        if bias is not None:
            if with_bias and phase in ("BEFORE_FALSE_EXTREME", "AT_FALSE_EXTREME") and trade.exit_reason == "SL":
                row["stopped_by_false_move"] = bool(_beyond(bias["false_price"], trade.stop, long))
            if with_bias:
                row["target_beyond_expansion"] = bool(not _beyond(trade.target, bias["exp_price"], long)
                                                      and trade.target != bias["exp_price"])
            row["fill_side"] = "FAVOURABLE" if _beyond(trade.fill, bias["open"], long) else "UNFAVOURABLE"
            swept = (inputs.contexts.get(str(trade.setup_id)) or {}).get("swept_level")
            if swept:
                row["raid_beyond_open"] = bool(_beyond(swept["price"], bias["open"], long))
                if swept.get("raided_at"):
                    raided = pd.Timestamp(swept["raided_at"]).tz_convert("UTC")
                    row["raid_in_candle"] = bool(bias_start <= raided < bias_end)
                row["raid_tf"], row["raid_source"] = swept.get("timeframe"), swept.get("source")
        bars = priced.get(trade.instrument)
        row["asof_shape"] = ("UNFORMED" if bars is None else
                             _asof_shape(bars, bias_start, bias_end, bar_ends[trade.instrument], filled, long))
        row["mode"] = _mode(with_bias, phase)
        rows.append(row)

    out = pd.DataFrame(rows, columns=list(columns))
    for name in columns:
        if name.endswith("_with") or name in ("stopped_by_false_move", "target_beyond_expansion",
                                              "raid_beyond_open", "raid_in_candle"):
            out[name] = pd.Series([None if v is None else bool(v) for v in out[name]], dtype=object)
    return out


# ── the split ───────────────────────────────────────────────────────────────

def split(table: pd.DataFrame, by: str, seed: int, resamples: int) -> pd.DataFrame:
    """Per value of ``by``: count, share, target-hit rate, mean net R with a 95%
    day-cluster interval (trading dates resampled), and the sum of net R."""
    columns = [by, "n", "share", "tp_rate", "mean_r", "lo", "hi", "sum_r"]
    if table.empty:
        return pd.DataFrame(columns=columns)
    keys = [k for k in pd.unique(table[by].astype(object).where(table[by].notna(), "n/a"))]
    order = ([m for m in FAILURE_MODES if m in keys] if by == "mode"
             else sorted(keys, key=lambda k: (str(type(k)), k)))
    values = table[by].astype(object).where(table[by].notna(), "n/a")
    rows = []
    for key in order:
        group = table[values == key]
        net = group["net_r"].astype(float).to_numpy()
        series = series_table(group["trading_date"], group["instrument"], {"r": (net, np.ones(len(net)))})
        ratios = Bootstrap(series, resamples, seed).ratios(series, "r")
        lo, hi = np.nanpercentile(ratios, [2.5, 97.5])
        rows.append({by: key, "n": len(group), "share": len(group) / len(table),
                     "tp_rate": float((group["exit_reason"] == "TP").mean()), "mean_r": float(net.mean()),
                     "lo": float(lo), "hi": float(hi), "sum_r": float(net.sum())})
    return pd.DataFrame(rows, columns=columns)
