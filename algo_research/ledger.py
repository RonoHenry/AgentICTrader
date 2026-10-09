"""The ledger: every official test and its result, append-only.

One place shows every question asked and its answer, so a pass is read
against the number of tries (Requirement 12).

- ``docs/research/ledger.csv``: one row per official test (a hypothesis, or
  one value of its ``[vary]``), appended by ``run`` and never rewritten.
- A rerun of a hypothesis whose hash is already in the ledger recomputes and
  compares with the recorded rows (Property 9); a different result is an
  error naming the differing fields. Another hash for an id already in the
  ledger is refused by ``run``: a changed question is a new hypothesis.
- ``docs/research/LEDGER.md``, rendered by ``python -m algo_research ledger``
  (and after each run), lists the tests by family with the passes chance
  alone would give: 2.5% per rule when nothing is there.

Numbers are written with 6 decimals, so a rerun compares exactly.

Validates: Requirements 8.3, 8.4, 12.1, 12.3 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import csv
import io
import math
from pathlib import Path
from typing import Optional, Sequence

from algo_research.runner import TestResult

__all__ = ["LEDGER_COLUMNS", "MAX_RULES", "RESULT_FIELDS", "append_rows", "ledger_row", "read_ledger",
           "render_ledger_md", "result_differences"]

MAX_RULES = 4
LEDGER_COLUMNS = (
    "seq", "run_at", "hypothesis", "test", "sha256", "family", "title", "slice", "snapshot", "code_commit",
    "measure", "n_events", "n_dates", "stat_name", "stat", "stat_lo", "stat_hi",
    *(f"{name}_{i}" for i in range(1, MAX_RULES + 1) for name in ("rule", "value", "baseline", "lo", "hi", "pass")),
    "verdict", "report",
)
#: What a rerun must reproduce: everything but when, where and in which order it ran.
RESULT_FIELDS = tuple(c for c in LEDGER_COLUMNS if c not in ("seq", "run_at", "code_commit", "report", "title",
                                                             "family"))


def _number(value: Optional[float]) -> str:
    return "" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value:.6f}"


def ledger_row(result: TestResult, *, seq: int, run_at: str, snapshot: str, code_commit: str, report: str) -> dict:
    h = result.test.hypothesis
    main = result.stats.get(result.main_stat)
    row = {
        "seq": str(seq), "run_at": run_at, "hypothesis": h.id, "test": result.test.name, "sha256": h.sha256 or "",
        "family": h.family, "title": h.title, "slice": result.slice, "snapshot": snapshot, "code_commit": code_commit,
        "measure": h.measure.kind, "n_events": str(result.n_events), "n_dates": str(result.n_dates),
        "stat_name": result.main_stat, "stat": _number(main.value if main else None),
        "stat_lo": _number(main.lo if main else None), "stat_hi": _number(main.hi if main else None),
        "verdict": result.verdict, "report": report,
    }
    for i in range(1, MAX_RULES + 1):
        outcome = result.outcomes[i - 1] if i <= len(result.outcomes) else None
        row[f"rule_{i}"] = "" if outcome is None else (
            f"{outcome.stat} vs {outcome.versus}" if outcome.versus else outcome.stat)
        row[f"value_{i}"] = _number(outcome.value) if outcome else ""
        row[f"baseline_{i}"] = _number(outcome.baseline) if outcome else ""
        row[f"lo_{i}"] = _number(outcome.lo) if outcome else ""
        row[f"hi_{i}"] = _number(outcome.hi) if outcome else ""
        row[f"pass_{i}"] = ("yes" if outcome.passed else "no") if outcome else ""
    return row


def read_ledger(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append_rows(path: Path, rows: Sequence[dict]) -> None:
    """Append ``rows``; the header is written only with the first row ever."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file() or path.stat().st_size == 0
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=LEDGER_COLUMNS, lineterminator="\n")
    if new:
        writer.writeheader()
    for row in rows:
        writer.writerow(row)
    with path.open("a", encoding="utf-8", newline="") as fh:
        fh.write(buffer.getvalue())


def result_differences(recorded: dict, now: dict) -> list[str]:
    return [name for name in RESULT_FIELDS if recorded.get(name, "") != now.get(name, "")]


def render_ledger_md(rows: Sequence[dict]) -> str:
    """docs/research/LEDGER.md: every official test by family, and what chance alone would pass."""
    lines = ["# AlgoResearch ledger", "",
             "Every official test (`python -m algo_research run`), in the order run. Rendered from "
             "`docs/research/ledger.csv` by `python -m algo_research ledger`; edit neither by hand.", ""]
    rules = sum(1 for r in rows for i in range(1, MAX_RULES + 1) if r.get(f"rule_{i}"))
    passes = sum(1 for r in rows if r["verdict"] == "PASS")
    lines += [f"- Official tests: **{len(rows)}**, judging {rules} rules.",
              f"- Passed: **{passes}**. Expected by chance if nothing is there: at most "
              f"**{0.025 * len(rows):.3f}** (2.5% per rule; a test passes only when every rule does).",
              f"- Insufficient samples: {sum(1 for r in rows if r['verdict'] == 'INSUFFICIENT')}.", ""]
    if not rows:
        lines.append("No official test has run yet.")
        return "\n".join(lines) + "\n"
    for family in sorted({r["family"] for r in rows}):
        mine = [r for r in rows if r["family"] == family]
        lines += [f"## {family}", "",
                  f"{len(mine)} test(s); {sum(1 for r in mine if r['verdict'] == 'PASS')} passed; "
                  f"{0.025 * len(mine):.3f} expected by chance.", "",
                  "| # | Test | Title | Slice | Events | Dates | Statistic | Rules | Verdict | Report |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in mine:
            test = f"{r['hypothesis']}[{r['test']}]" if r["test"] else r["hypothesis"]
            stat = f"{r['stat_name']} {r['stat']} [{r['stat_lo']}, {r['stat_hi']}]" if r["stat"] else r["stat_name"]
            verdicts = ", ".join(f"{r[f'rule_{i}']}: {r[f'pass_{i}']}" for i in range(1, MAX_RULES + 1)
                                 if r.get(f"rule_{i}"))
            report = f"[{Path(r['report']).name}]({Path(r['report']).relative_to('docs/research').as_posix()})" \
                if r["report"].startswith("docs/research/") else r["report"]
            lines.append(f"| {r['seq']} | {test} | {r['title']} | {r['slice']} | {r['n_events']} | {r['n_dates']} "
                         f"| {stat} | {verdicts} | **{r['verdict']}** | {report} |")
        lines.append("")
    return "\n".join(lines)
