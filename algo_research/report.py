"""Reports: one Markdown file per hypothesis run.

``run`` writes ``docs/research/reports/H<nnn>.md``; ``explore`` writes the same
report under ``data/research/drafts/`` (Requirement 12.2). Outline, per test
of the hypothesis:

1. the verdict line: the statistic with its interval, and each baseline;
2. the question as registered: the hypothesis file itself, and its hash;
3. the sample: events, dates and skipped rows; counts by instrument, year and weekday;
4. the results: each pass rule (statistic, comparison, interval, rule, result), then the other statistics;
5. stability: by instrument, quarter and weekday, and the share of quarters with the same sign;
6. races: outcomes, the ambiguous share ("needs tick data" above 10%), holding time, MFE/MAE quantiles;
7. check by eye: the first 20 event times per instrument, with direction and levels;
8. the inputs: snapshot and fingerprints, code commit, spec values, slice, seed, ledger rows.

The report holds no clock time, so two runs on one snapshot and commit write
the same bytes (Property 9).

Validates: Requirements 11.4, 12.2 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from algo_research.runner import TestResult

__all__ = ["ReportInputs", "render_report"]

_AMBIGUOUS_FLAG = 0.10


@dataclass(frozen=True)
class ReportInputs:
    snapshot: str
    fingerprints: Mapping[str, str]               # instrument -> "rows / sha256"
    code_commit: str
    specs: Mapping[str, Mapping[str, object]]     # instrument -> typical spread, slippage, commission
    hypothesis_text: str
    ledger_rows: Mapping[str, str] = field(default_factory=dict)   # test label -> ledger seq


def _cell(value) -> str:
    """An event column in the check-by-eye table: unknown values as a dash, times to the minute."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "–"
    if isinstance(value, float):
        return _f(value, 5)
    if isinstance(value, pd.Timestamp):
        return f"{value:%Y-%m-%d %H:%M}"
    return str(value)


def _f(value: Optional[float], digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "–"
    return f"{value:.{digits}f}"


def render_report(results: Sequence[TestResult], inputs: ReportInputs) -> str:
    h = results[0].test.hypothesis
    lines = [f"# {h.id}: {h.title}", ""]
    for r in results:
        lines.append(f"- {_verdict_line(r)}")
    lines += ["", "## The question as registered", "", f"sha256 `{h.sha256 or '–'}`", "", "```toml",
              inputs.hypothesis_text.replace("\r\n", "\n").strip("\n"), "```", ""]
    for r in results:
        title = f"Test {r.test.name}" if r.test.name else "Results"
        lines += [f"## {title}", ""]
        lines += _sample(r) + _results(r) + _stability(r) + _races(r) + _by_eye(r)
    lines += _inputs(results, inputs)
    return "\n".join(lines).rstrip("\n") + "\n"


def _verdict_line(r: TestResult) -> str:
    main = r.stats.get(r.main_stat)
    stat = f"{r.main_stat} {_f(main.value)} [{_f(main.lo)}, {_f(main.hi)}]" if main else r.main_stat
    baselines = ", ".join(f"{name} {_f(value)}" for name, value in r.baselines.items())
    name = f"{r.label}: " if r.test.name else ""
    return f"{name}**{r.verdict}** · {stat}" + (f" · {baselines}" if baselines else "") + \
        f" · {r.n_events} events on {r.n_dates} dates ({r.slice} slice)"


def _counts(series: pd.Series) -> str:
    counts = series.value_counts().sort_index()
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "–"


def _sample(r: TestResult) -> list[str]:
    measured = r.table[f"n:{r.main_stat}"] > 0 if len(r.table) else pd.Series(dtype=bool)
    events = r.events[measured.to_numpy()] if len(r.events) else r.events
    dates = pd.DatetimeIndex(events["trading_date"]) if len(events) else pd.DatetimeIndex([])
    weekdays = pd.Series([("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[d.weekday()] for d in dates],
                         dtype=object)
    skipped = ", ".join(f"{k} {v}" for k, v in sorted(r.skipped.items()) if v) or "none"
    lines = ["### Sample", "",
             f"- Events: {len(r.events)} fired, {r.n_events} measured, on {r.n_dates} trading dates.",
             f"- Skipped: {skipped}.",
             f"- By instrument: {_counts(events['instrument']) if len(events) else '–'}.",
             f"- By year: {_counts(pd.Series(dates.year)) if len(events) else '–'}.",
             f"- By weekday: {', '.join(f'{d} {n}' for d, n in weekdays.value_counts().reindex(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']).dropna().astype(int).items()) or '–'}."]
    if r.draws_available is not None and len(r.draws_available):
        low, high = int(r.draws_available.min()), int(r.draws_available.max())
        short = int((r.draws_available < high).sum())
        lines.append(f"- Random-time draws per event: {low} to {high}; {short} event(s) had fewer than the most.")
    if r.extra.get("starved"):
        mean, k = r.extra["starved"]
        lines.append(f"- **Random-time baseline starved:** {mean:.1f} draws per event on average, below K/2 = "
                     f"{k / 2:g}. Too few to judge by, so the verdict is INSUFFICIENT (Req 10.8).")
    return lines + [""]


def _results(r: TestResult) -> list[str]:
    lines = ["### Results", "", "| Statistic | Versus | Value | Baseline | Tested [95% interval] | Rule | Result |",
             "|---|---|---|---|---|---|---|"]
    for o in r.outcomes:
        tested = "difference" if o.versus else "value"
        lines.append(f"| {o.stat} | {o.versus or '–'} | {_f(o.value)} | {_f(o.baseline)} | {tested} "
                     f"{_f(o.estimate)} [{_f(o.lo)}, {_f(o.hi)}] | lower bound > {o.min_effect:g} | "
                     f"{'pass' if o.passed else 'fail'} |")
    lines += ["", "Every statistic of the measure, alone:", "", "| Statistic | Value [95% interval] |", "|---|---|"]
    for name, o in r.stats.items():
        lines.append(f"| {name} | {_f(o.value)} [{_f(o.lo)}, {_f(o.hi)}] |")
    return lines + [""]


def _stability(r: TestResult) -> list[str]:
    if not r.breakdowns:
        return ["### Stability", "", "No events.", ""]
    lines = ["### Stability", "", "The tested comparison per group (these inform; only the rules decide).", ""]
    for name in ("instrument", "quarter", "weekday"):
        table = r.breakdowns[name]
        lines += [f"| {name.capitalize()} | Events | Dates | Value | Baseline | Effect |", "|---|---|---|---|---|---|"]
        for row in table.itertuples():
            lines.append(f"| {row.group} | {row.events} | {row.dates} | {_f(row.value)} | {_f(row.baseline)} | "
                         f"{_f(row.effect)} |")
        lines.append("")
    lines += [f"Quarters with the overall effect's sign: {_f(r.breakdowns['same_sign_quarters'], 2)}.", ""]
    return lines


def _races(r: TestResult) -> list[str]:
    if r.races is None:
        return []
    races = r.races[r.races["outcome"].isin(["TARGET", "STOP", "TIMEOUT"])]
    lines = ["### Races", "", f"- Outcomes: {_counts(r.races['outcome'])}."]
    if len(races):
        ambiguous = float(races["ambiguous"].astype(bool).mean())
        flag = " **needs tick data**" if ambiguous > _AMBIGUOUS_FLAG else ""
        mfe, mae = races["mfe_r"].astype(float), races["mae_r"].astype(float)
        lines += [f"- Ambiguous bars (one M1 bar reached both stop and target; the stop won): "
                  f"{_f(ambiguous, 3)}{flag}.",
                  f"- Holding time: mean {_f(float(races['holding_minutes'].mean()), 1)} minutes.",
                  f"- MFE (R) quartiles: {', '.join(_f(q, 2) for q in mfe.quantile([0.25, 0.5, 0.75]))}; "
                  f"MAE (R) quartiles: {', '.join(_f(q, 2) for q in mae.quantile([0.25, 0.5, 0.75]))}."]
    return lines + [""]


def _by_eye(r: TestResult) -> list[str]:
    lines = ["### Check by eye", "", "The first 20 events per instrument. Times are the M15 close the event fired "
             "on.", ""]
    events = r.events
    races = getattr(r, "races", None)
    if races is not None:      # what was traded, for the chart
        events = events.join(races[["stop", "target", "outcome"]].rename(columns=lambda c: f"race_{c}"))
    levels = [c for c in events.columns if c not in ("row", "t", "instrument", "trading_date", "direction")]
    for instrument, part in events.groupby("instrument", sort=True):
        lines += [f"**{instrument}**", "", "| " + " | ".join(["t (UTC)", "New York", "Direction", *levels]) + " |",
                  "|" + "---|" * (3 + len(levels))]
        for row in part.head(20).itertuples(index=False):
            t = pd.Timestamp(row.t)
            local = t.tz_convert("America/New_York")
            values = [getattr(row, name) for name in levels]
            shown = [_cell(v) for v in values]
            lines.append("| " + " | ".join([f"{t:%Y-%m-%d %H:%M}", f"{local:%a %H:%M}", row.direction or "–", *shown])
                         + " |")
        lines.append("")
    if r.events.empty:
        lines += ["No events.", ""]
    return lines


def _inputs(results: Sequence[TestResult], inputs: ReportInputs) -> list[str]:
    lines = ["## Inputs", "", f"- Snapshot: `{inputs.snapshot}`"]
    lines += [f"  - {instrument}: {fp}" for instrument, fp in sorted(inputs.fingerprints.items())]
    lines.append(f"- Code commit: `{inputs.code_commit}`")
    lines.append("- Costs (spec file):")
    for instrument, spec in sorted(inputs.specs.items()):
        lines.append(f"  - {instrument}: " + ", ".join(f"{k} {v}" for k, v in spec.items()))
    for r in results:
        seq = inputs.ledger_rows.get(r.label)
        where = f"; ledger row {seq}" if seq else "; not in the ledger (explore)"
        lines.append(f"- {r.label}: slice {r.slice}, seed {r.seed}{where}")
    return lines + [""]
