"""
Tests for algo_backtester/pine.py — the engine's trades as a TradingView overlay.

Task 294 (.kiro/specs/algo-backtester/tasks.md, update 2026-10f). The overlay
is a Pine Script v6 indicator generated from a run directory: risk and reward
boxes, the decision label, the raided pool, the draw, the fill, the exit with
its result and failure mode, and each D1 open. Drawings appear only on the bar
of their event, so Bar Replay never shows an outcome early (D25).

The run is the autopsy tests' synthetic EURUSD week (T1-T9 closed, T10 open).
Validates: Requirements 13.1-13.7 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd
import pytest

from algo_backtester.autopsy import FAILURE_MODES
from algo_backtester.pine import MAX_TRADES, PineError, pine_float, pine_script, pine_string, write_pine
from tests.test_backtest_autopsy import M15, NONE, TRADES, bar, day, write_run

MON, THU = date(2026, 1, 12), date(2026, 1, 15)
TRADE_ARRAYS = ("tDec", "tFill", "tExit", "side", "entry", "stopPx", "tgtPx", "fillPx", "exitPx",
                "raidPx", "raidT0", "raidT1", "drawPx", "openTx", "exitTx", "modes")
DAY_ARRAYS = ("dStart", "dEnd", "dOpen")


def ms(t: pd.Timestamp) -> int:
    return int(t.value // 1_000_000)


def _args(body: str) -> list[str]:
    """Split array.from(...) arguments on commas outside string literals."""
    out, cur, quoted, escaped = [], [], False, False
    for ch in body:
        if quoted:
            cur.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
            cur.append(ch)
        elif ch == ",":
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def arrays(script: str) -> dict[str, tuple[str, list[str]]]:
    found = re.findall(r"var array<(\w+)> (\w+) = array\.from\((.*?)\)\n", script, re.S)
    return {name: (typ, _args(body)) for typ, name, body in found}


def decision(name: str) -> pd.Timestamp:
    trade = next(t for t in TRADES if t[0] == name)
    return bar(trade[2], trade[3]) - M15


@pytest.fixture
def run(tmp_path):
    return write_run(tmp_path)


@pytest.fixture
def script(run) -> str:
    return pine_script(run, "EURUSD", MON, THU, NONE)


# ── the script ─────────────────────────────────────────────────────────────

def test_header_and_inputs(script):
    assert script.startswith("//@version=6\n")
    header = re.search(r"indicator\((.*?)\)\n", script, re.S).group(1)
    for part in ("overlay = true", "max_boxes_count = 500", "max_lines_count = 500", "max_labels_count = 500"):
        assert part in header
    for title in ("Raided pool", "Draw on liquidity", "D1 open", "Result at exit"):
        assert f'"{title}' in script
    mode_input = next(line for line in script.splitlines() if "input.string" in line)
    assert "hindsight" in mode_input and '"ALL"' in mode_input
    assert all(f'"{m}"' in mode_input for m in FAILURE_MODES)


def test_trades_embedded_in_decision_order(script):
    a = arrays(script)
    order = ["T3", "T1", "T2", "T4", "T5", "T6", "T7", "T8", "T9"]
    assert a["tDec"] == ("int", [str(ms(decision(n))) for n in order])
    assert a["side"][1] == ["1", "1", "-1", "1", "-1", "1", "1", "1", "-1"]
    t1 = order.index("T1")
    assert float(a["entry"][1][t1]) == 1.0990 and float(a["stopPx"][1][t1]) == 1.0970
    assert float(a["tgtPx"][1][t1]) == 1.1050
    assert int(a["tExit"][1][t1]) == ms(bar(1, 50) + timedelta(minutes=5) + timedelta(hours=1))
    assert float(a["raidPx"][1][t1]) == 1.0960 and int(a["raidT1"][1][t1]) == ms(bar(1, 30))
    assert a["raidPx"][1][order.index("T3")] == "0.0"                       # no recorded raid
    assert "+1.60R" in a["exitTx"][1][t1] and "TP" in a["exitTx"][1][t1]
    assert "WITH_ON_TIME" in a["exitTx"][1][t1] and a["modes"][1][t1] == '"WITH_ON_TIME"'
    assert "LONG" in a["openTx"][1][t1] and "SSL" in a["openTx"][1][t1]
    assert "no raid" in a["openTx"][1][order.index("T3")]
    assert "WITH_ON_TIME" not in a["openTx"][1][t1]                          # hindsight only at the exit


def test_arrays_have_equal_lengths(script):
    a = arrays(script)
    assert set(TRADE_ARRAYS) | set(DAY_ARRAYS) <= set(a)
    assert {len(a[n][1]) for n in TRADE_ARRAYS} == {9}
    assert {len(a[n][1]) for n in DAY_ARRAYS} == {4}


def test_window_filters_instrument_and_trading_dates(run):
    tuesday = arrays(pine_script(run, "EURUSD", date(2026, 1, 13), date(2026, 1, 13), NONE))
    assert tuesday["tDec"][1] == [str(ms(decision("T5"))), str(ms(decision("T6")))]
    with pytest.raises(PineError, match="no trades"):
        pine_script(run, "GBPUSD", MON, THU, NONE)


def test_d1_opens_for_each_day_in_the_window(script):
    a = arrays(script)
    assert a["dStart"][1] == [str(ms(day(k))) for k in (1, 2, 3, 4)]
    assert a["dEnd"][1] == [str(ms(day(k + 1))) for k in (1, 2, 3, 4)]
    assert [float(v) for v in a["dOpen"][1]] == [1.1000] * 4


def test_floats_carry_a_decimal_point(script):
    assert pine_float(2632.0) == "2632.0" and pine_float(156.759615) == "156.759615" and pine_float(0) == "0.0"
    assert pine_float(1.10001) == "1.10001"
    for name, (typ, values) in arrays(script).items():
        if typ == "float":
            assert all(re.fullmatch(r"-?\d+\.\d+", v) for v in values), name


def test_strings_escaped():
    assert pine_string('a "b" \\ c\nd') == '"a \\"b\\" \\\\ c\\nd"'


def test_continuation_indent_is_not_a_multiple_of_four(script):
    inside = False
    for line in script.splitlines():
        if inside:
            indent = len(line) - len(line.lstrip(" "))
            assert indent % 4 != 0, line
        if "= array.from(" in line and not line.rstrip().endswith(")"):
            inside = True
        elif inside and line.rstrip().endswith(")"):
            inside = False


def test_refuses_empty_and_oversized_windows(run):
    with pytest.raises(PineError, match="no trades"):
        pine_script(run, "EURUSD", date(2026, 2, 1), date(2026, 2, 28), NONE)
    with pytest.raises(PineError, match="9 trades"):
        pine_script(run, "EURUSD", MON, THU, NONE, max_trades=3)
    assert MAX_TRADES == 120


def test_write_pine(run):
    path = write_pine(run, "EURUSD", MON, THU, NONE)
    assert path == run / "pine" / "EURUSD_2026-01-12_2026-01-15.pine"
    assert path.read_text(encoding="utf-8").startswith("//@version=6")
