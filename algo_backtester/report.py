"""A run's outputs: manifest.json, journal.csv, summary.json and summary.md.

    manifest = build_manifest(cfg, result, datas, specs, spec_source=spec_source(profile.spec_file),
                              engine_fingerprint=cache.engine_fingerprint, git=git_state(), created_at=now)
    run_dir = write_run(RUNS_DIR, cfg, manifest, result)     # data/backtests/<run_id>/

**manifest.json** records what makes the run reproducible (Req 8.1, 9.5):
- the code commit and dirty flag, and the engine code fingerprint;
- the resolved run config and strategy settings, and the broker profile;
- the instrument specs and where their costs came from;
- per instrument, the data range and fingerprint, warm-up sources and the
  bars priced at the typical spread;
- the hold-out and final-validation flags, and the AI-modifier and
  news-filter switches, both off in a backtest.

``run_id`` is the sha256 of that content, excluding ``created_at`` (and the
bootstrap seed, which is derived from the id). Identical inputs therefore
give the same id and byte-identical journal and summaries.

**journal.csv** has one row per SignalRecord that reached Phase B (Req 8.1),
skipped intents and their reasons included, with the levels and times to find
each trade on a chart (Req 8.6):
- rows are sorted by (t, instrument);
- prices have 6 decimals, R 4, lots 5, confidence 2; times are ISO 8601 UTC;
- a cell is empty where the field doesn't apply;
- an order still open at the end shows what is known, with exit_reason
  OPEN_AT_END.

**summary.json / summary.md** are metrics.summarize() of the whole run, and of
each walk-forward window when there are several (Req 7.3). Buckets with fewer
than ``min_trades`` trades are marked insufficient evidence (Req 8.4).

Validates: Requirements 8.1, 8.4, 8.6, 9.5 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Union

from agent.instruments import InstrumentSpecs
from algo_backtester.config import REPO_ROOT, RunConfig
from algo_backtester.data import InstrumentData
from algo_backtester.metrics import Stats, Summary, summarize
from algo_backtester.run import RunResult
from algo_backtester.sim_broker import ClosedTrade, SimTrade
from algo_backtester.simulation import JournalRow

__all__ = [
    "JOURNAL_COLUMNS",
    "RUNS_DIR",
    "GitState",
    "build_manifest",
    "git_state",
    "journal_csv",
    "run_id",
    "spec_source",
    "stats_cells",
    "stats_from_json",
    "summary_json",
    "summary_md",
    "write_run",
]

RUNS_DIR = REPO_ROOT / "data" / "backtests"
_NOT_HASHED = ("run_id", "bootstrap_seed", "created_at")

JOURNAL_COLUMNS = (
    # identity and decision
    "t", "instrument", "setup_id", "grade", "decision", "reason", "killzone", "time_window",
    # the setup
    "direction", "entry", "stop", "target", "r_ratio", "confidence",
    # the order
    "order_id", "order_kind", "placed_at", "expires_at", "filled_at", "fill", "ideal_fill",
    "closed_at", "exit", "ideal_exit", "exit_reason", "lots",
    # results
    "gross_r", "net_r", "cost_r_spread", "cost_r_slippage", "cost_r_commission", "mae_r", "mfe_r",
    "holding_minutes", "cost_flag",
)


# ── manifest ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GitState:
    commit: str
    dirty: bool


def git_state(root: Path = REPO_ROOT) -> GitState:
    """HEAD and whether tracked files have changes. Untracked files don't
    count: a stray note mustn't mark every run dirty, and the engine code
    fingerprint covers the engine sources whatever git knows of them."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout

    return GitState(commit=git("rev-parse", "HEAD").strip(),
                    dirty=bool(git("status", "--porcelain", "--untracked-files=no").strip()))


def spec_source(spec_file: Path) -> Optional[str]:
    """The spec file's ``# Source:`` line: the broker account its costs were exported from."""
    for line in Path(spec_file).read_text(encoding="utf-8").splitlines():
        if line.startswith("# Source:"):
            return line[len("# Source:"):].strip()
    return None


def build_manifest(cfg: RunConfig, result: RunResult, datas: Mapping[str, InstrumentData], specs: InstrumentSpecs,
                   *, spec_source: Optional[str], engine_fingerprint: str, git: GitState,
                   created_at: datetime) -> dict:
    start, end = _midnight(cfg.run.start), _midnight(cfg.run.end)
    content = {
        "git_commit": git.commit,
        "git_dirty": git.dirty,
        "engine_code_fingerprint": engine_fingerprint,
        "broker_profile": cfg.run.profile,
        "instrument_spec_source": spec_source,
        **result.manifest,                       # study, holdout_start, final_validation, variant, windows
        "ai_modifiers": "disabled",
        "news_filter": "not_applied",
        "run_config": cfg.model_dump(mode="json"),
        "strategy_config": cfg.strategy.model_dump(mode="json"),
        "instrument_specs": {i: asdict(specs[i]) for i in cfg.run.instruments},
        "data": {i: {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": datas[i].fingerprint.rows,          # every row used, M1 and native warm-up
            "sha256": datas[i].fingerprint.sha256,
            "m1_rows": len(datas[i].m1),
            "warmup_source_by_tf": dict(datas[i].warmup_source),
            "default_spread_bars": result.floored_bars.get(i, 0),
            "coverage_problems": list(datas[i].coverage.problems),
        } for i in cfg.run.instruments},
    }
    identity = run_id(content)
    return {"run_id": identity, **content, "bootstrap_seed": int(identity[:8], 16),
            "created_at": created_at.isoformat()}


def run_id(manifest: Mapping[str, Any]) -> str:
    """sha256 of the manifest's canonical JSON, without created_at, run_id and bootstrap_seed."""
    content = {k: v for k, v in manifest.items() if k not in _NOT_HASHED}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ── journal ────────────────────────────────────────────────────────────────

def journal_csv(journal: Sequence[JournalRow], open_orders: Iterable[SimTrade] = ()) -> str:
    still_open = {order.order_id: order for order in open_orders}
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(JOURNAL_COLUMNS)
    for row in sorted(journal, key=lambda r: (r.t, r.instrument)):
        values = _journal_values(row, still_open.get(row.order_id))
        writer.writerow("" if values[c] is None else values[c] for c in JOURNAL_COLUMNS)
    return out.getvalue()


def _journal_values(row: JournalRow, open_order: Optional[SimTrade]) -> dict:
    intent, trade = row.intent, row.trade
    order: Union[ClosedTrade, SimTrade, None] = trade or open_order
    filled = trade is not None and trade.filled
    values = {
        "t": _time(row.t), "instrument": row.instrument, "setup_id": row.setup_id, "grade": row.grade,
        "decision": row.decision, "reason": row.reason,
        "killzone": row.context.killzone if row.context else None, "time_window": row.time_window,
        "direction": intent.direction if intent else None,
        "entry": _num(intent and intent.entry, 6), "stop": _num(intent and intent.stop_loss, 6),
        "target": _num(intent and intent.take_profit_1, 6), "r_ratio": _num(intent and intent.r_ratio, 4),
        "confidence": _num(intent and intent.confidence, 2),
        "order_id": row.order_id,
        "order_kind": order.kind if order else None,
        "placed_at": _time(order and order.placed_at), "expires_at": _time(order and order.expires_at),
        "filled_at": _time(order and order.filled_at),
        "fill": _num(order and order.fill, 6), "ideal_fill": _num(order and order.ideal_fill, 6),
        "closed_at": _time(trade and trade.closed_at), "exit": _num(trade and trade.exit, 6),
        "ideal_exit": _num(trade and trade.ideal_exit, 6),
        "exit_reason": trade.exit_reason if trade else ("OPEN_AT_END" if open_order else None),
        "lots": _num(order and order.lots, 5),
        "holding_minutes": round(trade.holding_time.total_seconds() / 60) if filled else None,
        "cost_flag": ("true" if trade.cost_flag else "false") if filled else None,
    }
    for name in ("gross_r", "net_r", "cost_r_spread", "cost_r_slippage", "cost_r_commission", "mae_r", "mfe_r"):
        values[name] = _num(getattr(trade, name) if filled else None, 4)
    return values


def _num(value: Optional[float], decimals: int) -> Optional[str]:
    return None if value is None else f"{value:.{decimals}f}"


def _time(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


# ── summaries ──────────────────────────────────────────────────────────────

Windows = Sequence[tuple[datetime, datetime, Summary]]


def summary_json(summary: Summary, windows: Windows = ()) -> str:
    body = _summary_dict(summary)
    if windows:
        body["windows"] = [{"start": s.isoformat(), "end": e.isoformat(), **_summary_dict(w)} for s, e, w in windows]
    return json.dumps(body, indent=2) + "\n"


def summary_md(summary: Summary, manifest: Mapping[str, Any], min_trades: int, windows: Windows = ()) -> str:
    data = next(iter(manifest["data"].values()), {})
    lines = [
        f"# Backtest {manifest['run_id'][:12]}",
        "",
        f"- run_id: `{manifest['run_id']}`",
        f"- profile: {manifest['broker_profile']} (costs from: {manifest['instrument_spec_source'] or 'unknown'})",
        f"- variant: {manifest['variant'] or 'base'}",
        f"- data: {data.get('start', '?')[:10]} to {data.get('end', '?')[:10]} (UTC, end exclusive), "
        f"instruments: {', '.join(manifest['data'])}",
        f"- study: {manifest['study']}, hold-out from {manifest['holdout_start']}, "
        f"final validation: {'yes' if manifest['final_validation'] else 'no'}",
        f"- code: {manifest['git_commit'][:12]} (dirty: {'yes' if manifest['git_dirty'] else 'no'}), "
        f"engine {manifest['engine_code_fingerprint'][:12]}",
        f"- ai_modifiers: {manifest['ai_modifiers']} · news_filter: {manifest['news_filter']}",
        "",
        f"*Insufficient evidence*: buckets with n < {min_trades} trades are shown in italics and marked "
        f"\"insufficient\". They are not findings (Req 8.4).",
        "",
        "## Overall",
        "",
        *_stats_table([("all trades", summary.overall)], first="", wide=True),
        "",
        _counts_line(summary.counts),
    ]
    for name, buckets in summary.breakdowns.items():
        lines += ["", f"## By {name.replace('_', ' ')}", "", *_stats_table(list(buckets.items()), first=name)]
    if windows:
        lines += ["", "## Walk-forward windows", "", *_stats_table(
            [(f"{s:%Y-%m-%d} to {e:%Y-%m-%d}", w.overall) for s, e, w in windows], first="window")]
    return "\n".join(lines) + "\n"


def _summary_dict(summary: Summary) -> dict:
    return {
        "overall": _stats_dict(summary.overall),
        "breakdowns": {name: {k: _stats_dict(v) for k, v in buckets.items()}
                       for name, buckets in summary.breakdowns.items()},
        "counts": summary.counts,
    }


def _stats_dict(stats: Stats) -> dict:
    def plain(value):
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, tuple):
            return [plain(v) for v in value]
        return value

    return {f.name: plain(getattr(stats, f.name)) for f in fields(stats)}


_COLUMNS_WIDE = ("trades", "win rate", "avg gross R", "avg net R", "expectancy R (95% CI)", "profit factor",
                 "max DD R", "max DD %", "losing streak", "avg hold (min)", "avg cost R", "cost share", "evidence")
_COLUMNS = ("trades", "win rate", "avg net R", "expectancy R (95% CI)", "profit factor", "max DD R",
            "cost share", "evidence")


def stats_cells(s: Stats) -> dict[str, str]:
    """A Stats as display strings, keyed by column name (as in summary.md)."""
    return {
        "trades": str(s.trades),
        "win rate": _pct(s.win_rate),
        "avg gross R": _r(s.avg_gross_r),
        "avg net R": _r(s.avg_net_r),
        "expectancy R (95% CI)": _r(s.expectancy_r) + (
            f" ({_r(s.expectancy_ci[0])} to {_r(s.expectancy_ci[1])})" if s.expectancy_ci else ""),
        "profit factor": "–" if s.profit_factor is None else f"{s.profit_factor:.2f}",
        "max DD R": f"{s.max_drawdown_r:.2f}",
        "max DD %": f"{s.max_drawdown_pct:.2f}%",
        "losing streak": str(s.longest_losing_streak),
        "avg hold (min)": "–" if s.avg_holding_minutes is None else f"{s.avg_holding_minutes:.0f}",
        "avg cost R": _r(s.avg_cost_r),
        "cost share": _pct(s.cost_share),
        "evidence": s.evidence,
    }


def stats_from_json(values: Mapping[str, Any]) -> Stats:
    """A Stats back from summary.json."""
    ci = values["expectancy_ci"]
    return Stats(**{**values, "expectancy_ci": tuple(ci) if ci is not None else None})


def _stats_table(rows: Sequence[tuple[str, Stats]], first: str, wide: bool = False) -> list[str]:
    columns = _COLUMNS_WIDE if wide else _COLUMNS
    out = [f"| {first} | " + " | ".join(columns) + " |", "|" + "---|" * (len(columns) + 1)]
    for label, s in rows:
        cells = stats_cells(s)
        insufficient = s.evidence == "insufficient"
        values = [f"*{cells[c]}*" if insufficient and cells[c] != "–" else cells[c] for c in columns if c != "evidence"]
        out.append(f"| {label} | " + " | ".join(values) + f" | {s.evidence} |")
    return out


def _counts_line(counts: Mapping[str, Any]) -> str:
    decisions = ", ".join(f"{k} {v}" for k, v in counts["decisions"].items())
    return (f"Journal rows {counts['rows']}; orders {counts['orders']}: {counts['filled']} filled, "
            f"{counts['unfilled']} never filled, {counts['open_at_end']} open at the end. Decisions: {decisions}.")


def _r(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:+.2f}"


def _pct(value: Optional[float]) -> str:
    return "–" if value is None else f"{value:.0%}"


# ── the run directory ──────────────────────────────────────────────────────

def write_run(root: Path, cfg: RunConfig, manifest: Mapping[str, Any], result: RunResult) -> Path:
    """Write ``root/<run_id>/``. The summaries' bootstrap is seeded from the run id."""
    def summary_of(journal: Sequence[JournalRow]) -> Summary:
        return summarize(journal, cfg.account.initial_equity, cfg.report.min_trades,
                         cfg.report.bootstrap_resamples, manifest["bootstrap_seed"])

    overall = summary_of(result.journal)
    windows = ([(w.start, w.end, summary_of(w.result.journal)) for w in result.windows]
               if len(result.windows) > 1 else [])
    run_dir = Path(root) / manifest["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "manifest.json": json.dumps(manifest, indent=2) + "\n",
        "journal.csv": journal_csv(result.journal, result.open_orders),
        "summary.json": summary_json(overall, windows),
        "summary.md": summary_md(overall, manifest, cfg.report.min_trades, windows),
    }
    for name, text in outputs.items():
        (run_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return run_dir


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
