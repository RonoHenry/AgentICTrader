"""The engine's trades on the trader's own TradingView charts.

``pine_script(run_dir, instrument, start, end)`` turns a run's filled trades into
a Pine Script v6 indicator (.kiro/specs/algo-backtester, update 2026-10f,
Requirement 13). Pasted into TradingView's Pine Editor, it draws on the chart:

- each trade's risk box (entry to stop) and reward box (entry to target), from
  its decision until its exit, with a label at the decision (direction, grade,
  the pool its setup raided);
- the raided pool, a dotted line from where it formed to where it was raided;
- the draw on liquidity, a dashed line while the trade is open;
- a marker at the fill, and a label at the exit: result in R, exit reason and
  the trade's failure mode from the trade autopsy;
- each D1 candle's open (17:00 New York).

Bar Replay shows nothing early (D25): every drawing is created on the chart bar
that contains its event's time, an open trade's boxes grow bar by bar, and the
hindsight (result, exit reason, failure mode) appears only on the exit's bar.

Everything comes from the run directory: the journal, the recorded context
and the run's own candles (on the narrative's price basis). Times are UNIX
milliseconds, which ``xloc.bar_time`` reads, so the chart's time zone doesn't
matter. Prices are the run's (Exness bid); another feed may sit a pip or so
away. Pine shows at most 500 boxes, lines and labels, so a script holds at
most ``MAX_TRADES`` trades (D26): about a year of one instrument at the BODY
run's pace, usually a month is plenty.

    python -m algo_backtester pine data/backtests/<run_id> --instrument EURUSD --month 2025-03

Validates: Requirements 13.1-13.7 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from algo_backtester.autopsy import FAILURE_MODES, autopsy_table, load_run
from algo_research.narrative import NarrativeConfig, apply_price_basis, load_narrative_config, narrate
from liquidity_engine.models import Timeframe
from services.market_data.strategy_calendar import StrategyCalendar

__all__ = ["MAX_TRADES", "PineError", "pine_float", "pine_script", "pine_string", "write_pine"]

MAX_TRADES = 120                     # D26: 3 labels, 2 boxes and 2 lines a trade; Pine shows 500 of each
_PER_LINE = 8                        # array literal values per source line
_INDENT = " " * 6                    # Pine continuation lines: any indent that isn't a multiple of 4
_NY = "America/New_York"
_SERVER_SHIFT = timedelta(hours=7)
_CALENDAR = StrategyCalendar()


class PineError(Exception):
    """A window the overlay can't hold: no trades, or more than MAX_TRADES."""


def pine_float(value: Any) -> str:
    """A Pine float literal: always with a decimal point, never exponent notation."""
    text = f"{float(value):.6f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def pine_string(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _ms(t: Any) -> int:
    return int(pd.Timestamp(t).tz_convert("UTC").value // 1_000_000)


def _trading_date(t: pd.Timestamp) -> date:
    start = pd.Timestamp(_CALENDAR.period_start(t.to_pydatetime(), Timeframe.D1))
    return (start.tz_convert(_NY).tz_localize(None) + _SERVER_SHIFT).date()


def _array(typ: str, name: str, values: Sequence[str]) -> str:
    chunks = [", ".join(values[i:i + _PER_LINE]) for i in range(0, len(values), _PER_LINE)]
    head = f"var array<{typ}> {name} = array.from({chunks[0]}"
    if len(chunks) == 1:
        return head + ")"
    return "\n".join([head + ","] + [_INDENT + c + "," for c in chunks[1:-1]] + [_INDENT + chunks[-1] + ")"])


def _exit_price(row: Any) -> float:
    exit_price = getattr(row, "exit", None)
    if exit_price is not None and not (isinstance(exit_price, float) and math.isnan(exit_price)):
        return float(exit_price)
    return float(row.target if row.exit_reason == "TP" else row.stop if row.exit_reason == "SL" else row.fill)


def _decision_text(row: Any, context: Mapping[str, Any]) -> str:
    swept = context.get("swept_level") or {}
    raid = (f"raid {swept.get('side', '')} {swept.get('source', '')} ({swept.get('timeframe', '')})".replace("  ", " ")
            if swept else "no raid recorded")
    grade = getattr(row, "grade", None)
    grade_text = f" grade {grade}" if isinstance(grade, str) and grade else ""
    return f"{row.direction}{grade_text}\n{raid}"


def pine_script(run_dir: Path, instrument: str, start: date, end: date, cfg: Optional[NarrativeConfig] = None,
                max_trades: int = MAX_TRADES) -> str:
    """The overlay for ``instrument``'s filled trades decided on trading dates in [start, end]."""
    run_dir = Path(run_dir)
    cfg = cfg or load_narrative_config()
    inputs = load_run(run_dir)
    journal = inputs.journal.reset_index(drop=True)
    modes = autopsy_table(inputs, cfg)["mode"].reset_index(drop=True)
    decided = pd.to_datetime(journal["t"], utc=True)
    dates = pd.Series([_trading_date(t) for t in decided], index=journal.index)
    mask = (journal["instrument"] == instrument) & (dates >= start) & (dates <= end)
    picked = (journal[mask].assign(decided_at=decided[mask], failure_mode=modes[mask])
              .sort_values("decided_at", kind="stable"))
    if picked.empty:
        raise PineError(f"no trades of {instrument} decided from {start} to {end} in run {inputs.run_id}")
    if len(picked) > max_trades:
        raise PineError(f"{len(picked)} trades of {instrument} from {start} to {end}: more than the overlay's "
                        f"{max_trades}; choose a shorter window")

    cols: dict[str, list[str]] = {name: [] for name in (
        "tDec", "tFill", "tExit", "side", "entry", "stopPx", "tgtPx", "fillPx", "exitPx",
        "raidPx", "raidT0", "raidT1", "drawPx", "openTx", "exitTx", "modes")}
    for row in picked.itertuples(index=False):
        context = inputs.contexts.get(str(row.setup_id)) or {}
        swept = context.get("swept_level") or {}
        draw = context.get("draw_on_liquidity") or {}
        cols["tDec"].append(str(_ms(row.decided_at)))
        cols["tFill"].append(str(_ms(row.filled_at)))
        cols["tExit"].append(str(_ms(row.closed_at)))
        cols["side"].append("1" if row.direction == "LONG" else "-1")
        for name, value in (("entry", row.entry), ("stopPx", row.stop), ("tgtPx", row.target),
                            ("fillPx", row.fill), ("exitPx", _exit_price(row))):
            cols[name].append(pine_float(value))
        cols["raidPx"].append(pine_float(swept.get("price") or 0.0))
        cols["raidT0"].append(str(_ms(swept["formed_at"])) if swept.get("formed_at") else "0")
        cols["raidT1"].append(str(_ms(swept["raided_at"])) if swept.get("raided_at") else "0")
        cols["drawPx"].append(pine_float(draw.get("price") or 0.0))
        cols["openTx"].append(pine_string(_decision_text(row, context)))
        cols["exitTx"].append(pine_string(f"{row.net_r:+.2f}R {row.exit_reason}\n{row.failure_mode}"))
        cols["modes"].append(pine_string(row.failure_mode))

    bars = apply_price_basis(inputs.bars[instrument], instrument, cfg.price_basis)
    days = narrate(bars, inputs.bar_tf, Timeframe.D1)
    days = days[[start <= _trading_date(s) <= end for s in days["start"]]]
    if days.empty:
        raise PineError(f"no candles of {instrument} from {start} to {end} in run {inputs.run_id}")

    types = {"tDec": "int", "tFill": "int", "tExit": "int", "side": "int", "raidT0": "int", "raidT1": "int",
             "openTx": "string", "exitTx": "string", "modes": "string"}
    data = [_array(types.get(name, "float"), name, values) for name, values in cols.items()]
    data += [_array("int", "dStart", [str(_ms(s)) for s in days["start"]]),
             _array("int", "dEnd", [str(_ms(e)) for e in days["end"]]),
             _array("float", "dOpen", [pine_float(o) for o in days["open"]])]
    options = ", ".join(pine_string(m) for m in ("ALL", *FAILURE_MODES))
    return _TEMPLATE.format(
        title=pine_string(f"Engine {instrument} {start}"), instrument=instrument,
        command=f"python -m algo_backtester pine {run_dir.as_posix()} --instrument {instrument} "
                f"--start {start} --end {end}",
        run_id=inputs.run_id, n=len(picked), start=start, end=end, options=options,
        data="\n".join(data), instrument_literal=pine_string(instrument))


def write_pine(run_dir: Path, instrument: str, start: date, end: date, cfg: Optional[NarrativeConfig] = None,
               max_trades: int = MAX_TRADES) -> Path:
    """Write the overlay to <run_dir>/pine/<instrument>_<start>_<end>.pine; returns its path."""
    script = pine_script(run_dir, instrument, start, end, cfg, max_trades)
    out = Path(run_dir) / "pine" / f"{instrument}_{start}_{end}.pine"
    out.parent.mkdir(exist_ok=True)
    out.write_text(script, encoding="utf-8", newline="\n")
    return out


_TEMPLATE = """//@version=6
indicator({title}, overlay = true, max_boxes_count = 500, max_lines_count = 500, max_labels_count = 500)

// Generated by: {command}
// Run {run_id}: the engine's {n} filled trades of {instrument} decided on trading dates {start} to {end}.
// Each drawing appears on the bar of its event, so Bar Replay shows nothing early; the result and the
// failure mode (hindsight) appear only at the exit. Times are UTC milliseconds, so the chart's time zone
// doesn't matter. Prices are the run's (Exness bid); another feed may sit a pip or so away.
// Regenerate rather than edit.

showRaid = input.bool(true, "Raided pool")
showDraw = input.bool(true, "Draw on liquidity")
showOpen = input.bool(true, "D1 open (17:00 New York)")
showExit = input.bool(true, "Result at exit: R, exit reason, failure mode (hindsight)")
modeSel = input.string("ALL", "Only this failure mode (hindsight; ALL for a blind replay)", options = [{options}])

// The trades, in decision order. A raid or draw of 0 means none was recorded.
{data}

var int nTrades = array.size(tDec)
var array<box> riskBox = array.new<box>(nTrades)
var array<box> rewardBox = array.new<box>(nTrades)
var array<line> drawLine = array.new<line>(nTrades)
var array<int> openTrades = array.new<int>()
var int nextTrade = 0
var int nextDay = 0

// D1 opens, each drawn when its day starts
while nextDay < array.size(dStart) and array.get(dStart, nextDay) < time_close
    if showOpen
        line.new(array.get(dStart, nextDay), array.get(dOpen, nextDay), array.get(dEnd, nextDay), array.get(dOpen, nextDay), xloc = xloc.bar_time, color = color.new(color.gray, 30), style = line.style_dotted, width = 1)
    nextDay += 1

// Trades decided in this bar: the position boxes, the decision label, the raided pool and the draw
while nextTrade < nTrades and array.get(tDec, nextTrade) < time_close
    i = nextTrade
    nextTrade += 1
    if modeSel == "ALL" or array.get(modes, i) == modeSel
        t0 = array.get(tDec, i)
        e = array.get(entry, i)
        s = array.get(stopPx, i)
        g = array.get(tgtPx, i)
        isLong = array.get(side, i) > 0
        array.set(riskBox, i, box.new(t0, math.max(e, s), t0, math.min(e, s), xloc = xloc.bar_time, border_color = color.new(color.red, 40), bgcolor = color.new(color.red, 82)))
        array.set(rewardBox, i, box.new(t0, math.max(e, g), t0, math.min(e, g), xloc = xloc.bar_time, border_color = color.new(color.teal, 40), bgcolor = color.new(color.teal, 82)))
        if showRaid and array.get(raidPx, i) > 0
            line.new(array.get(raidT0, i), array.get(raidPx, i), array.get(raidT1, i), array.get(raidPx, i), xloc = xloc.bar_time, color = color.orange, style = line.style_dotted, width = 2)
        if showDraw and array.get(drawPx, i) > 0
            array.set(drawLine, i, line.new(t0, array.get(drawPx, i), t0, array.get(drawPx, i), xloc = xloc.bar_time, color = color.blue, style = line.style_dashed, width = 1))
        label.new(t0, s, array.get(openTx, i), xloc = xloc.bar_time, style = isLong ? label.style_label_up : label.style_label_down, color = color.new(color.gray, 15), textcolor = color.white, size = size.small)
        array.push(openTrades, i)

// Open trades: the fill marker, the boxes growing bar by bar, and at the exit the result
if array.size(openTrades) > 0
    for j = array.size(openTrades) - 1 to 0
        i = array.get(openTrades, j)
        tFillI = array.get(tFill, i)
        if tFillI >= time and tFillI < time_close
            label.new(tFillI, array.get(fillPx, i), "", xloc = xloc.bar_time, style = label.style_xcross, color = color.yellow, size = size.tiny, tooltip = "fill " + str.tostring(array.get(fillPx, i)))
        tExitI = array.get(tExit, i)
        done = tExitI < time_close
        x2 = done ? tExitI : time_close
        box.set_right(array.get(riskBox, i), x2)
        box.set_right(array.get(rewardBox, i), x2)
        dl = array.get(drawLine, i)
        if not na(dl)
            line.set_x2(dl, x2)
        if done
            if showExit
                label.new(tExitI, array.get(exitPx, i), array.get(exitTx, i), xloc = xloc.bar_time, style = label.style_label_left, color = color.new(color.gray, 15), textcolor = color.white, size = size.small)
            array.remove(openTrades, j)

// The overlay is for one instrument
if barstate.islast and not str.contains(syminfo.ticker, {instrument_literal})
    label.new(bar_index, high, "This overlay is for {instrument}; this chart is " + syminfo.ticker, style = label.style_label_down, color = color.orange, textcolor = color.black)
"""
