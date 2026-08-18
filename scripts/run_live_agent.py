"""Standalone live runner — pulls real MT5 candles for one or more
instruments, runs each through the real ICT liquidity-engine detection +
grading, and for every one that grades, drives the actual AgentGraph
decide/execute loop against a real (demo) MT5 account via MT5BrokerAdapter.

This is the first end-to-end wiring of "key in credentials, model does the
rest": no fabricated setups, no mocked broker. Instruments are processed
sequentially against one shared AgentGraph/RiskEngine/Redis state, not on
separate threads — MT5's Python API is a single shared IPC connection to
the terminal, so concurrent OS threads calling into it would race against
each other for no real benefit (per-instrument grading is pure in-process
Python anyway, sub-second even for a handful of pairs). "Concurrent" here
means every configured pair is evaluated in the same pass against a shared
risk state, so the max-concurrent-trades limit is enforced *across* pairs,
not that MT5 calls happen in parallel.

If the live market currently has no A+/A/B-grade setup on a given
instrument/timeframe, this reports that honestly and moves on — it does
not force a trade.

Known gaps:
  - RiskEngine.compute_position_size() (services/risk_engine/main.py)
    returns equity * 1% / sl_pips, a figure designed for unit-based
    brokers (OANDA). MT5BrokerAdapter passes that value straight through
    as lot volume, which is a real unit mismatch — untouched, a normal
    account equity would compute to several standard lots. This runner
    seeds a small, explicit demo equity via Redis (_DEMO_EQUITY below) so
    the resulting order size stays sane; it does not fix the underlying
    mismatch.
  - Nothing in agent/nodes/execute_node.py or learn_node.py writes an
    incremented `open_trades` back to Redis after a successful fill, so
    RiskEngine's "max concurrent trades" check is a structural no-op in
    production today — it only ever sees whatever open_trades was last
    seeded with. This runner works around that locally (see
    _bump_open_trades below) so the cap is actually honored *within this
    one run* across the instrument basket; it does not fix the underlying
    gap in execute_node/learn_node.

Usage:
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_live_agent.py \\
        [--timeframe M15] [--instruments EURUSD,GBPUSD,USDJPY] [--min-rr 3.0]
"""
from __future__ import annotations

import os

# Must be set before numpy/MetaTrader5 are imported — works around an
# OpenBLAS "memory allocation failed" crash seen in this environment.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import fakeredis
from decouple import Config, RepositoryEnv

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import MetaTrader5 as mt5

from agent.brokers.factory import create_broker_client
from agent.graph import AgentGraph
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import BiasDirection, Candle, SetupGrade, Timeframe
from ml.features.session_features import TimeWindowClassifier
from services.risk_engine.main import RiskEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_live_agent")

config = Config(RepositoryEnv(str(REPO_ROOT / ".env")))

DEFAULT_INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
# D1/W1 are always pulled (LiquidityMappingEngine hard-requires them). The
# full intraday HTF stack (H12/H8/H6/H4/H3) is pulled too as bias/CRT-phase
# context — HTFBiasClassifier computes a bias for every timeframe it's
# given, so this is what actually lets H4 (or H12/H8/H6/H3) inform intraday
# directional bias distinctly from D1/W1's swing bias, rather than just
# sitting there computed-but-unused. None of these drive entry-array
# selection though — only the CLI-selectable entry timeframe (--timeframe,
# M15-and-below) does, per liquidity_engine.grader.setup_grader.
# _ENTRY_ELIGIBLE_TIMEFRAMES — HTF is bias/context only, trading entries
# come from M15 and below.
CONTEXT_TIMEFRAMES = (Timeframe.H12, Timeframe.H8, Timeframe.H6, Timeframe.H4, Timeframe.H3)
ENTRY_TIMEFRAME = Timeframe.M15
_ENTRY_TIMEFRAME_CHOICES = (Timeframe.M1, Timeframe.M3, Timeframe.M5, Timeframe.M15)
_MT5_TIMEFRAME = {
    Timeframe.M1: mt5.TIMEFRAME_M1,
    Timeframe.M3: mt5.TIMEFRAME_M3,
    Timeframe.M5: mt5.TIMEFRAME_M5,
    Timeframe.M15: mt5.TIMEFRAME_M15,
    Timeframe.H3: mt5.TIMEFRAME_H3,
    Timeframe.H4: mt5.TIMEFRAME_H4,
    Timeframe.H6: mt5.TIMEFRAME_H6,
    Timeframe.H8: mt5.TIMEFRAME_H8,
    Timeframe.H12: mt5.TIMEFRAME_H12,
    Timeframe.D1: mt5.TIMEFRAME_D1,
    Timeframe.W1: mt5.TIMEFRAME_W1,
}
_CANDLE_COUNT = {
    Timeframe.M1: 300,
    Timeframe.M3: 300,
    Timeframe.M5: 300,
    Timeframe.M15: 200,
    Timeframe.H3: 150,
    Timeframe.H4: 150,
    Timeframe.H6: 120,
    Timeframe.H8: 100,
    Timeframe.H12: 90,
    Timeframe.D1: 90,
    Timeframe.W1: 30,
}

_GRADE_TO_CONFIDENCE = {
    SetupGrade.A_PLUS: 0.90,
    SetupGrade.A: 0.80,
    SetupGrade.B: 0.70,
}

# See module docstring — a deliberately small equity so RiskEngine's
# equity/pip position-size formula lands near a sane MT5 micro-lot for a
# smoke test, instead of the several-standard-lots a real account equity
# would compute to given the current unit mismatch.
_DEMO_EQUITY = 200.0


class _InMemoryJournal:
    """Minimal stand-in for a PyMongo Collection — Redis/Mongo aren't
    running locally for this smoke test, so trade_journal writes just go
    to memory and get printed at the end instead of persisted."""

    def __init__(self) -> None:
        self._docs: list[dict] = []

    def insert_one(self, document: dict):
        self._docs.append(document)
        return SimpleNamespace(inserted_id=len(self._docs))

    def count_documents(self, _filter: dict) -> int:
        return len(self._docs)


def _fetch_candles(symbol: str, tf: Timeframe, instrument: str) -> list[Candle]:
    rates = mt5.copy_rates_from_pos(symbol, _MT5_TIMEFRAME[tf], 0, _CANDLE_COUNT[tf])
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No {tf.value} candles returned for {symbol}: {mt5.last_error()}")
    return [
        Candle(
            timestamp=datetime.fromtimestamp(int(r["time"]), tz=timezone.utc),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=int(r["tick_volume"]),
            timeframe=tf,
            instrument=instrument,
        )
        for r in rates
    ]


def _bump_open_trades(redis_client, user_id: str) -> None:
    """Increment the shared exposure key's open_trades count by 1.

    Works around the real production gap noted in the module docstring:
    execute_node/learn_node never write this back themselves. Called after
    every successful fill in this run so RiskEngine's max-concurrent-trades
    check sees an accurate count for the *next* instrument in the basket.
    """
    key = f"risk:exposure:{user_id}"
    exposure = json.loads(redis_client.get(key))
    exposure["open_trades"] += 1
    redis_client.set(key, json.dumps(exposure))


# Standard Deviation projection levels used for targets (see
# liquidity_engine.projections.standard_deviation) — TTrades' own
# reference material explicitly labels the 2.5 level as "Target" on its
# projection chart, with 4.0 as a further runner target.
_TP1_SD_LEVEL = 2.5
_TP2_SD_LEVEL = 4.0


def _pick_sd_targets(liquidity_map, entry: float, direction: str) -> tuple[float, float | None]:
    """Standard Deviation projection targets replace the earlier crude
    draw_on_liquidity.price stand-in used for take_profit_1.

    Falls back to draw_on_liquidity.price (TP2 left unset) when
    sd_projection is unavailable (no displacement leg found), or when its
    direction — derived from D1 bias inside the engine — disagrees with
    this trade's actual direction (derived from the entry array itself,
    which can differ from D1 bias, see the direction-inference comment
    above) and would land the target on the wrong side of entry.
    """
    sd = liquidity_map.sd_projection
    if sd is not None:
        tp1 = sd.targets.get(_TP1_SD_LEVEL)
        tp2 = sd.targets.get(_TP2_SD_LEVEL)
        lands_correctly = tp1 is not None and (
            (direction == "LONG" and tp1 > entry) or (direction == "SHORT" and tp1 < entry)
        )
        if lands_correctly:
            return tp1, tp2
    return liquidity_map.draw_on_liquidity.price, None


def _build_patterns(liquidity_map) -> list[dict]:
    patterns = []
    if liquidity_map.unicorn is not None:
        patterns.append({"type": "UNICORN", "confidence": 0.85})
    if liquidity_map.sweep_detected:
        patterns.append({"type": "LIQUIDITY_SWEEP", "confidence": 0.75})
    if liquidity_map.cisd_cascade is not None and liquidity_map.cisd_cascade.cascade_valid:
        patterns.append({"type": "CISD_CASCADE", "confidence": 0.75})
    return patterns


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeframe",
        default=ENTRY_TIMEFRAME.value,
        choices=sorted(tf.value for tf in _ENTRY_TIMEFRAME_CHOICES),
        help=(
            "Entry timeframe to grade setups on — M15 and below only; "
            f"D1/W1/{'/'.join(tf.value for tf in CONTEXT_TIMEFRAMES)} are always pulled too as "
            "HTF bias/context but never drive entry-array selection "
            "(see setup_grader._ENTRY_ELIGIBLE_TIMEFRAMES)."
        ),
    )
    parser.add_argument(
        "--instruments",
        default=",".join(DEFAULT_INSTRUMENTS),
        help="Comma-separated instrument list to evaluate in one pass (default: %(default)s).",
    )
    parser.add_argument(
        "--min-rr",
        type=float,
        default=3.0,
        help="Minimum reward:risk to act on a graded setup, regardless of letter grade (default: %(default)s).",
    )
    return parser.parse_args()


def _process_instrument(
    instrument: str,
    entry_tf: Timeframe,
    symbol_suffix: str,
    graph: AgentGraph,
    redis_client,
    min_rr: float,
) -> dict:
    """Fetch, grade, and (if warranted) trade one instrument. Returns a
    summary dict for the end-of-run table — never raises for a NO_TRADE
    outcome, only for real fetch/connectivity failures."""
    mt5_symbol = f"{instrument}{symbol_suffix}"
    mt5.symbol_select(mt5_symbol, True)

    context_tf_labels = "/".join(tf.value for tf in CONTEXT_TIMEFRAMES)
    logger.info("Fetching D1/W1/%s/%s candles for %s...", context_tf_labels, entry_tf.value, mt5_symbol)
    candles_by_tf = {
        Timeframe.D1: _fetch_candles(mt5_symbol, Timeframe.D1, instrument),
        Timeframe.W1: _fetch_candles(mt5_symbol, Timeframe.W1, instrument),
        **{tf: _fetch_candles(mt5_symbol, tf, instrument) for tf in CONTEXT_TIMEFRAMES},
        entry_tf: _fetch_candles(mt5_symbol, entry_tf, instrument),
    }

    now = datetime.now(tz=timezone.utc)
    liquidity_map = LiquidityMappingEngine().analyze(candles_by_tf, instrument, now)
    print("\n" + liquidity_map.to_agent_context() + "\n")

    setup_grade = liquidity_map.setup_grade
    if setup_grade is None or setup_grade.grade == SetupGrade.NO_TRADE:
        reason = setup_grade.grade_reason if setup_grade else "no grade computed"
        print(f"[{instrument}] No valid setup right now — {reason}")
        return {"instrument": instrument, "grade": "NO_TRADE", "decision": None, "trade_id": None}

    d1_bias = liquidity_map.htf_bias[Timeframe.D1.value]

    entry = setup_grade.suggested_entry
    stop_loss = setup_grade.suggested_stop

    # Direction must come from the entry/stop relationship itself, not the
    # overall D1 bias: SetupGrader picks whichever unfilled PD array has the
    # highest strength_score for suggested_entry/suggested_stop, and that
    # array's own polarity (which can be a countertrend micro-structure
    # array) — not the D1 bias — is what _suggested_stop actually places the
    # stop relative to (BEARISH array -> stop above entry; BULLISH -> stop
    # below). Inferring from D1 bias instead caused a stop placed on the
    # wrong side of entry, which MT5 correctly rejected.
    direction = "LONG" if stop_loss < entry else "SHORT"
    take_profit_1, take_profit_2 = _pick_sd_targets(liquidity_map, entry, direction)
    r_ratio = abs(take_profit_1 - entry) / abs(entry - stop_loss)

    if r_ratio < min_rr:
        print(f"[{instrument}] Graded {setup_grade.grade.value} but R:R {r_ratio:.2f} is below the {min_rr} floor — skipping.")
        return {"instrument": instrument, "grade": setup_grade.grade.value, "decision": f"SKIP (R:R {r_ratio:.2f} < {min_rr})", "trade_id": None}

    current_price = candles_by_tf[entry_tf][-1].close
    time_features = TimeWindowClassifier().classify(
        now,
        instrument,
        current_price=current_price,
        daily_open=candles_by_tf[Timeframe.D1][-1].open,
        weekly_open=candles_by_tf[Timeframe.W1][-1].open,
    )

    message = {
        "setup_id": str(uuid.uuid4()),
        "instrument": instrument,
        "timeframe": entry_tf.value,
        "direction": direction,
        "raw_confidence": _GRADE_TO_CONFIDENCE[setup_grade.grade],
        "detected_at": now.isoformat(),
        "regime": f"TRENDING_{d1_bias.direction.value}",
        "patterns": _build_patterns(liquidity_map),
        "mode": "AUTONOMOUS",
        "trade_plan": {
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "r_ratio": r_ratio,
            "recommended_size": 0.01,
        },
        "time_window": time_features.time_window,
        "narrative_phase": time_features.narrative_phase,
        "time_window_weight": time_features.time_window_weight,
        "is_killzone": time_features.is_killzone,
        "price_vs_daily_open": time_features.price_vs_daily_open,
        "price_vs_weekly_open": time_features.price_vs_weekly_open,
    }

    print(f"[{instrument}] Setup graded {setup_grade.grade.value} — {direction}")
    print(
        f"  entry={entry}  stop_loss={stop_loss}  take_profit_1={take_profit_1}"
        f"  take_profit_2={take_profit_2}  r_ratio={r_ratio:.2f}"
    )
    print(f"  time_window={time_features.time_window} (killzone={time_features.is_killzone})")
    print(f"[{instrument}] Handing off to AgentGraph (mode=AUTONOMOUS)...\n")

    final_state = graph.run(message)

    print(f"[{instrument}] decision={final_state.decision}  reason={final_state.decision_reason}")
    if final_state.error:
        print(f"[{instrument}] error: {final_state.error}")

    if final_state.broker_order_id:
        _bump_open_trades(redis_client, "demo-runner")

    return {
        "instrument": instrument,
        "grade": setup_grade.grade.value,
        "decision": final_state.decision.value if final_state.decision else None,
        "trade_id": final_state.trade_id,
    }


def main() -> None:
    args = _parse_args()
    entry_tf = Timeframe(args.timeframe)
    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]

    symbol_suffix = config("MT5_SYMBOL_SUFFIX", default="")
    mt5_path = config("MT5_PATH", default="") or None
    init_kwargs = {
        "login": config("MT5_LOGIN", cast=int),
        "password": config("MT5_PASSWORD"),
        "server": config("MT5_SERVER"),
    }
    if mt5_path:
        init_kwargs["path"] = mt5_path

    logger.info("Connecting to MT5...")
    if not mt5.initialize(**init_kwargs):
        code, desc = mt5.last_error()
        raise RuntimeError(f"MT5 initialize failed ({code}): {desc}")

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set(
        "risk:exposure:demo-runner",
        json.dumps({"daily_dd_pct": 0.0, "weekly_dd_pct": 0.0, "open_trades": 0, "equity": _DEMO_EQUITY}),
    )

    broker_client = create_broker_client(
        "mt5",
        login=init_kwargs["login"],
        password=init_kwargs["password"],
        server=init_kwargs["server"],
        path=mt5_path,
        symbol_suffix=symbol_suffix,
    )

    graph = AgentGraph(
        redis_client=redis_client,
        risk_engine=RiskEngine(redis_client),
        fcm_sender=None,
        broker_client=broker_client,
        trade_journal_collection=_InMemoryJournal(),
        user_id="demo-runner",
    )

    print(
        f"Evaluating {len(instruments)} instrument(s) on {entry_tf.value} "
        f"(min R:R {args.min_rr}): {', '.join(instruments)}\n"
    )

    results = []
    for instrument in instruments:
        try:
            results.append(
                _process_instrument(instrument, entry_tf, symbol_suffix, graph, redis_client, args.min_rr)
            )
        except Exception as exc:
            logger.error("[%s] failed: %s", instrument, exc)
            results.append({"instrument": instrument, "grade": "ERROR", "decision": str(exc), "trade_id": None})

    mt5.shutdown()

    print("\n=== Summary ==================================================")
    print(f"{'instrument':<10} {'grade':<10} {'decision':<25} trade_id")
    for r in results:
        print(f"{r['instrument']:<10} {r['grade']:<10} {str(r['decision']):<25} {r['trade_id'] or ''}")


if __name__ == "__main__":
    main()
