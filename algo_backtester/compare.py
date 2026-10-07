"""Runs side by side (Req 8.5).

    print(compare([run_a, run_b]))                  # overall figures, one column per run
    print(compare([run_a, run_b], by="killzone"))   # one breakdown, bucket by bucket

Each run is read from its directory (manifest.json and summary.json), so any
two finished runs can be compared later. Runs on different data are refused,
because their numbers don't measure the same thing: a different instrument
set, data range, row count or data fingerprint. Different code, strategy
settings or costs are what a comparison is for, and the table shows them.

Validates: Requirements 8.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from algo_backtester.metrics import Stats
from algo_backtester.report import stats_cells, stats_from_json

__all__ = ["ComparisonError", "compare"]

_DATA_FIELDS = ("start", "end", "rows", "sha256")
_METRICS = ("trades", "win rate", "avg gross R", "avg net R", "expectancy R (95% CI)", "profit factor", "max DD R",
            "max DD %", "losing streak", "avg hold (min)", "avg cost R", "cost share", "evidence")


class ComparisonError(ValueError):
    """The runs can't be compared."""


@dataclass(frozen=True)
class _Run:
    manifest: dict
    summary: dict

    @property
    def label(self) -> str:
        return f"{self.manifest['variant'] or 'base'} {self.manifest['run_id'][:8]}"

    def stats(self, by: Optional[str] = None) -> dict[str, Stats]:
        if by is None:
            return {"all": stats_from_json(self.summary["overall"])}
        return {bucket: stats_from_json(s) for bucket, s in self.summary["breakdowns"][by].items()}


def compare(run_dirs: Sequence[Path], by: Optional[str] = None) -> str:
    if len(run_dirs) < 2:
        raise ComparisonError("compare needs at least two runs")
    runs = [_load(Path(d)) for d in run_dirs]
    _check_same_data(runs)
    if by is not None:
        available = runs[0].summary["breakdowns"]
        if by not in available:
            raise ComparisonError(f"no breakdown {by!r}; available: {', '.join(available)}")
        return "\n".join(_breakdown_table(runs, by)) + "\n"
    return "\n".join(_overall_table(runs)) + "\n"


def _load(run_dir: Path) -> _Run:
    def read(name: str) -> dict:
        return json.loads((run_dir / name).read_text(encoding="utf-8"))

    return _Run(manifest=read("manifest.json"), summary=read("summary.json"))


def _check_same_data(runs: Sequence[_Run]) -> None:
    first, problems = runs[0], []
    for run in runs[1:]:
        a, b = first.manifest["data"], run.manifest["data"]
        if set(a) != set(b):
            problems.append(f"instruments: {', '.join(sorted(a))} in {first.label}, "
                            f"{', '.join(sorted(b))} in {run.label}")
        for instrument in sorted(set(a) & set(b)):
            for field in _DATA_FIELDS:
                if a[instrument][field] != b[instrument][field]:
                    problems.append(f"{instrument} {field}: {a[instrument][field]} in {first.label}, "
                                    f"{b[instrument][field]} in {run.label}")
    if problems:
        raise ComparisonError("runs on different data can't be compared:\n  " + "\n  ".join(problems))


def _overall_table(runs: Sequence[_Run]) -> list[str]:
    def code(m: dict) -> str:
        return m["git_commit"][:12] + (" (dirty)" if m["git_dirty"] else "")

    lines = [f"| metric | " + " | ".join(r.label for r in runs) + " |", "|" + "---|" * (len(runs) + 1)]
    lines.append("| code | " + " | ".join(code(r.manifest) for r in runs) + " |")
    lines.append("| engine | " + " | ".join(r.manifest["engine_code_fingerprint"][:12] for r in runs) + " |")
    lines.append("| final validation | " + " | ".join(
        "yes" if r.manifest["final_validation"] else "no" for r in runs) + " |")
    cells = [stats_cells(r.stats()["all"]) for r in runs]
    lines += [f"| {metric} | " + " | ".join(c[metric] for c in cells) + " |" for metric in _METRICS]
    return lines


def _breakdown_table(runs: Sequence[_Run], by: str) -> list[str]:
    per_run = [r.stats(by) for r in runs]
    buckets = sorted({bucket for stats in per_run for bucket in stats})
    lines = [f"| {by} | " + " | ".join(r.label for r in runs) + " |", "|" + "---|" * (len(runs) + 1)]
    for bucket in buckets:
        cells = []
        for stats in per_run:
            s = stats.get(bucket)
            if s is None:
                cells.append("–")
                continue
            c = stats_cells(s)
            cells.append(f"{c['avg net R']} R, n={s.trades}" + (" (insufficient)" if s.evidence == "insufficient" else ""))
        lines.append(f"| {bucket} | " + " | ".join(cells) + " |")
    return lines
