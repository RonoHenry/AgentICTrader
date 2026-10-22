"""The thesis run and its score (market-narrative Requirement 16.5-16.6, task 350).

    python -m algo_research.thesis run   --instruments XAUUSD [--limit 25] [--max-calls 30] [--effort medium]
    python -m algo_research.thesis score [--model <id>]
    python -m algo_research.thesis export --model <id> --out <file>     # the engine's thesis file (Requirement 17)

``run`` goes through the exploration slice's trading days in a fixed shuffled order (so a short run samples the
whole slice), builds the blind facts at each 17:00 New York open, asks the model, and keeps one file per day:

    data/research/theses/<model>/<instrument>/<trading date>.json

with the facts' hash, the answer, the thesis in real prices, the model, tokens, cost and time, and the score: DRAW,
INVALIDATED or NEITHER by the day's close, the coin's chance from the two distances, and the direction against the
day's close (``algo_research.replay.scoring.score_thesis``, as the trader's blind reads are scored). A day already
kept is skipped, and every model call is cached, so a stopped run resumes where it stopped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from algo_backtester.config import REPO_ROOT
from algo_research.config import trading_date_open
from algo_research.replay.scoring import _interval, score_thesis
from algo_research.thesis.llm import BudgetExhausted, LLMClient, config_from_env
from algo_research.thesis.prompt import messages_for, parse_answer

__all__ = ["THESES_DIR", "export", "main", "run", "score"]

THESES_DIR = REPO_ROOT / "data" / "research" / "theses"
UTC = timezone.utc
WARMUP_DAYS = 120


def _slug(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def trading_days(first: date, end: date, seed: int = 16) -> list[date]:
    """The weekdays of [first, end), in a fixed shuffled order."""
    days = [first + timedelta(days=k) for k in range((end - first).days) if (first + timedelta(days=k)).weekday() < 5]
    order = np.random.default_rng(seed).permutation(len(days))
    return [days[i] for i in order]


def _ask(client: LLMClient, facts, effort: Optional[str]) -> tuple[dict, list]:
    """The model's thesis, retried once when the answer isn't the fixed form; the replies, for the record."""
    messages = messages_for(facts)
    reasoning = {"effort": effort} if effort else None
    replies = []
    reply = client.complete(messages, reasoning=reasoning)
    replies.append(reply)
    try:
        return {"thesis": parse_answer(reply.text, facts.rescale), "error": None}, replies
    except ValueError as exc:
        retry = messages + [{"role": "assistant", "content": reply.text},
                            {"role": "user", "content": f"That was not the fixed form ({exc}). Answer again with only "
                                                        "the JSON object."}]
        reply = client.complete(retry, reasoning=reasoning)
        replies.append(reply)
        try:
            return {"thesis": parse_answer(reply.text, facts.rescale), "error": None}, replies
        except ValueError as exc2:
            return {"thesis": None, "error": str(exc2)}, replies


def run(instruments: list[str], first: date, end: date, limit: Optional[int], client: LLMClient,
        effort: Optional[str], root: Path = THESES_DIR, snapshot: Optional[Path] = None) -> list[dict]:
    from agent.strategy_config import StrategyConfig
    from algo_backtester.data import load_instrument
    from algo_backtester.watch import SnapshotSource
    from algo_research.config import load_research_config
    from algo_research.fractal_poi import FractalPOI, FractalSettings
    from algo_research.snapshot import SNAPSHOTS_DIR
    from algo_research.thesis.facts import facts_at

    snap = Path(snapshot) if snapshot else SNAPSHOTS_DIR / load_research_config().snapshot
    cfg = StrategyConfig(fvg_zone="gap")
    out_dir = root / _slug(client.cfg.model)
    kept = []
    for inst in instruments:
        source = SnapshotSource(snap)
        start = datetime.combine(first, datetime.min.time(), tzinfo=UTC) - timedelta(days=3)
        stop = datetime.combine(end, datetime.min.time(), tzinfo=UTC) + timedelta(days=2)
        data = load_instrument(source, inst, start, stop, cfg, None, venue="binance", max_gap_minutes=10_000)
        m1 = source._frame(inst)
        m1 = m1[(m1["time"] >= pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)) & (m1["time"] < pd.Timestamp(stop))]
        m1 = m1[["time", "open", "high", "low", "close"]].reset_index(drop=True)
        days = trading_days(first, end)
        if limit:
            days = days[:limit]
        # the indicator reads forward only: build it per day in date order, its readers stepped along
        readers = {"H1": FractalPOI(m1, "H1", FractalSettings(), inst), "H4": FractalPOI(m1, "H4", FractalSettings(), inst)}
        times = m1["time"]
        for day in sorted(days):
            path = out_dir / inst / f"{day.isoformat()}.json"
            if path.is_file():
                kept.append(json.loads(path.read_text(encoding="utf-8")))
                continue
            t = trading_date_open(day)
            close_t = trading_date_open(day + timedelta(days=1))                 # the D1 candle's close
            rows = m1[(times >= pd.Timestamp(t)) & (times < pd.Timestamp(close_t))]
            if len(rows) < 60:
                continue                                                       # a holiday or a gap
            try:
                facts = facts_at(data, cfg, t, readers)
            except (ValueError, KeyError, IndexError) as exc:
                print(f"{inst} {day}: no facts ({exc})", file=sys.stderr)
                continue
            try:
                answer, replies = _ask(client, facts, effort)
            except BudgetExhausted as exc:
                print(f"stopped: {exc}", file=sys.stderr)
                return kept
            thesis = answer["thesis"]
            open_price, close = float(rows["open"].iloc[0]), float(rows["close"].iloc[-1])
            direction = "UP" if close > open_price else "DOWN" if close < open_price else "FLAT"
            read = thesis.as_read() if thesis else {"bias": "NO_THESIS"}
            record = {
                "instrument": inst, "trading_date": day.isoformat(), "weekday": facts.weekday,
                "open": open_price, "rescale": {"open": facts.rescale.open, "atr": facts.rescale.atr},
                "facts_sha256": hashlib.sha256(facts.text.encode()).hexdigest(),
                "thesis": None if thesis is None else {
                    "bias": thesis.bias, "draw": thesis.draw, "invalidation": thesis.invalidation,
                    "draw_scaled": thesis.draw_scaled, "invalidation_scaled": thesis.invalidation_scaled,
                    "confidence": thesis.confidence, "reason": thesis.reason},
                "error": answer["error"],
                "answer": replies[-1].text, "model": replies[-1].model,
                "usage": [r.usage for r in replies], "cost": sum(r.cost for r in replies),
                "seconds": sum(r.seconds for r in replies), "cached": all(r.cached for r in replies),
                "score": score_thesis(read, rows.rename(columns=str), open_price, direction),
                "day_direction": direction,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
            kept.append(record)
            s = record["score"]
            print(f"{inst} {day} {read['bias']:9s} {s['outcome']:11s} p_coin {s['p_coin'] if s['p_coin'] is None else round(s['p_coin'], 2)}"
                  f"  day {direction}  {record['seconds']:.0f}s  ${record['cost']:.4f}", flush=True)
    return kept


def score(root: Path = THESES_DIR, model: Optional[str] = None) -> str:
    rows = []
    for path in sorted(root.glob("*/*/*.json")):
        if path.parent.parent.name == "cache" or (model and path.parent.parent.name != _slug(model)):
            continue
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    if not rows:
        return "no theses yet"
    lines = []
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        by_model.setdefault(r["model"], []).append(r)
    for model_dir, g in by_model.items():
        thesis = [r for r in g if r["thesis"] and r["thesis"]["bias"] != "NO_THESIS"]
        hits = [1.0 if r["score"]["outcome"] == "DRAW" else 0.0 for r in thesis]
        dates = [r["trading_date"] for r in thesis]
        known = [r for r in thesis if r["score"]["direction_right"] is not None]
        dirs = [1.0 if r["score"]["direction_right"] else 0.0 for r in known]
        p_coin = float(np.mean([r["score"]["p_coin"] for r in thesis])) if thesis else float("nan")
        lo, hi = _interval(hits, dates) if len(hits) > 1 else (float("nan"), float("nan"))
        dlo, dhi = _interval(dirs, [r["trading_date"] for r in known]) if len(dirs) > 1 else (float("nan"), float("nan"))
        errors = sum(1 for r in g if r.get("error"))
        lines += [f"model {model_dir}: {len(g)} days, {len(thesis)} with a thesis, {len(g) - len(thesis)} neutral "
                  f"({errors} unreadable answers); cost ${sum(r['cost'] for r in g):.3f}",
                  f"  DRAW before invalidation: {np.mean(hits) if hits else float('nan'):.0%} [{lo:.0%}, {hi:.0%}] "
                  f"against the coin's {p_coin:.0%}",
                  f"  direction right (the day's close): {np.mean(dirs) if dirs else float('nan'):.0%} [{dlo:.0%}, {dhi:.0%}]"]
    return "\n".join(lines)


def export(model: str, out: Path, root: Path = THESES_DIR) -> dict:
    """The kept theses of ``model`` as the engine's thesis file: {instrument: {trading date: side}}. A day the model
    couldn't answer is NO_THESIS."""
    table: dict[str, dict[str, str]] = {}
    for path in sorted((root / _slug(model)).glob("*/*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        side = (r.get("thesis") or {}).get("bias") or "NO_THESIS"
        table.setdefault(r["instrument"], {})[r["trading_date"]] = side
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=1, sort_keys=True), encoding="utf-8")
    return table


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m algo_research.thesis")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--instruments", nargs="+", default=["XAUUSD"])
    r.add_argument("--first", default="2025-01-01")
    r.add_argument("--end", default="2025-07-01")
    r.add_argument("--limit", type=int)
    r.add_argument("--max-calls", type=int, default=30)
    r.add_argument("--effort", default="medium", help="reasoning effort: low, medium, high, or none")
    r.add_argument("--model")
    s = sub.add_parser("score")
    s.add_argument("--model")
    e = sub.add_parser("export")
    e.add_argument("--model", required=True)
    e.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    if args.command == "export":
        table = export(args.model, args.out)
        print(f"wrote {args.out}: " + ", ".join(f"{k} {len(v)} days" for k, v in table.items()))
        return 0
    if args.command == "score":
        print(score(model=args.model))
        return 0
    overrides = {"max_calls": args.max_calls, **({"model": args.model} if args.model else {})}
    client = LLMClient(config_from_env(**overrides))
    run(args.instruments, date.fromisoformat(args.first), date.fromisoformat(args.end), args.limit, client,
        None if args.effort == "none" else args.effort)
    print(score(model=client.cfg.model))
    print(f"calls {client.calls}, cost ${client.cost:.4f}")
    return 0
