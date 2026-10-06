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

Both gaps noted in earlier revisions of this docstring are now fixed at
the source rather than worked around here:
  - RiskEngine.validate() now also returns risk_amount (equity *
    RISK_PER_TRADE, broker-agnostic money terms) alongside the OANDA-unit
    position_size. execute_node forwards it as order["risk_amount"], and
    MT5BrokerAdapter._compute_lots_from_risk() converts that into real MT5
    lots using the symbol's own trade_tick_value/trade_tick_size — no more
    treating an OANDA-unit figure as if it were already a lot count.
  - execute_node now calls RiskEngine.increment_open_trades() itself after
    every successful fill, so the max-concurrent-trades gate reflects real
    state in production, not just within a single run of this script (the
    _bump_open_trades workaround that used to live here is gone — it would
    now double-count against execute_node's own increment).
_DEMO_EQUITY is kept as a deliberately small seed equity regardless — a
smoke test placing several-standard-lot orders against a real demo account
the moment risk_amount happens to be large is still not something to risk
by default.

The agent message now also carries the same candle window already fetched
above (candles_by_tf), and AgentGraph is constructed with real
VisualModelClient/AlgoRAGSyncClient instances — both previously-missing
pieces of "AgentGraph decide/execute loop" above. Concretely: observe_node
used to re-derive liquidity_map=None (candles_by_tf was absent from the
message), and AgentGraph never had a visual_model_client to pass to
analyse_node at all, so the grade-gated visual-model/AlgoRAG calls in
analyse_node were dead code in this runner even for an A+ setup. They now
actually fire — requires services/visual_model + services/algorag (+
qdrant) running via docker-compose and a real ANTHROPIC_API_KEY in .env;
both clients degrade to a neutral result rather than failing the run if
those aren't up.

--feed binance swaps the candle source for Binance spot klines
(services/market_data/binance.py) so the loop can run on 24/7 crypto when
FX is closed — the MT5 demo server lists no crypto CFDs, and MT5 isn't
touched at all with that feed.

--broker picks what an approved setup turns into: mt5 (real demo orders,
the default for --feed mt5), paper (agent/brokers/paper.py simulates
fills against live M1 candles and scores each trade in R — the default
for --feed binance), or none (HUMAN_IN_LOOP: the alert is printed, no
order). --loop re-evaluates at every entry-timeframe bar close until
--duration minutes pass or Ctrl+C, then prints the paper-trade report;
paper trades persist to --paper-state so a forward test survives restarts.

For unattended runs (docker/paper-trader): --store-candles upserts every
fetched candle into TimescaleDB so the candles table stays current,
--heartbeat touches a file after each pass with fresh data (the container
health check), a feed outage ends the pass early instead of retrying
every request, and paper trades catch up across downtime from their
last processed M1 bar.

Usage:
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python scripts/run_live_agent.py \\
        [--feed mt5|binance] [--timeframe M15] [--instruments EURUSD,GBPUSD,USDJPY] [--min-rr 3.0]
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
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import fakeredis
from decouple import AutoConfig

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import MetaTrader5 as mt5
except ImportError:  # Linux/Docker: only --feed binance is available
    mt5 = None

from agent.algorag_client import AlgoRAGSyncClient
from agent.brokers.factory import create_broker_client
from agent.brokers.paper import PaperBrokerAdapter
from agent.graph import AgentGraph
from agent.order_intent import NoTrade, build_order_intent
from agent.strategy_config import ENTRY_TIMEFRAMES, StrategyConfig
from agent.visual_model_client import VisualModelClient
from liquidity_engine import LiquidityMappingEngine
from liquidity_engine.models import Candle, Timeframe
from services.market_data.binance import BinanceKlineClient, BinanceUnavailable
from services.market_data.candle_store import CandleStore
from services.market_data.mt5_clock import MT5ServerClock, NY_CLOSE
from services.risk_engine.main import RiskEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_live_agent")

# Environment variables win; the repo .env is the fallback (absent in Docker).
config = AutoConfig(search_path=str(REPO_ROOT))
# MT5 bar times are broker server time, not UTC — see services/market_data/mt5_clock.py.
_SERVER_CLOCK = MT5ServerClock(config("MT5_SERVER_TIMEZONE", default=NY_CLOSE))

DEFAULT_INSTRUMENTS = {
    "mt5": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
    "binance": ["BTCUSDT", "ETHUSDT"],
}
# Which timeframes are analysed, how many bars of each, min R:R, targets and
# grade confidence all live in agent.strategy_config.StrategyConfig, shared
# with AlgoBacktester; --timeframe and --min-rr override its defaults.
_MT5_TIMEFRAME = {} if mt5 is None else {
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
# See module docstring — a deliberately small equity so RiskEngine's
# equity/pip position-size formula lands near a sane MT5 micro-lot for a
# smoke test, instead of the several-standard-lots a real account equity
# would compute to given the current unit mismatch.
_DEMO_EQUITY = 200.0
_USER_ID = "demo-runner"
_ENTRY_TF_SECONDS = {Timeframe.M1: 60, Timeframe.M3: 180, Timeframe.M5: 300, Timeframe.M15: 900}
_PAPER_STATE = REPO_ROOT / "data" / "paper_trades.json"

# services/visual_model and services/algorag: docker-compose publishes both
# to localhost for a host-run script; inside the compose network (the
# paper-trader container) the env vars point at the service names instead.
# Both clients degrade gracefully to a neutral result if these aren't
# running, so it's always safe to wire them in.
_VISUAL_MODEL_URL = config("VISUAL_MODEL_URL", default="http://localhost:8005")
_ALGORAG_URL = config("ALGORAG_URL", default="http://localhost:8003")
# Feed errors that mean "the feed is down", not "this symbol failed" — the
# rest of the pass is skipped rather than retried instrument by instrument.
_FEED_DOWN = (BinanceUnavailable,)


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


def _fetch_candles(symbol: str, tf: Timeframe, instrument: str, count: int) -> list[Candle]:
    rates = mt5.copy_rates_from_pos(symbol, _MT5_TIMEFRAME[tf], 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No {tf.value} candles returned for {symbol}: {mt5.last_error()}")
    return [
        Candle(
            timestamp=_SERVER_CLOCK.to_utc(r["time"]),
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


def _fetch_binance_candles(client: BinanceKlineClient, instrument: str, tf: Timeframe, count: int) -> list[Candle]:
    klines = client.latest(instrument, tf.value, count)
    if not klines:
        raise RuntimeError(f"No {tf.value} candles returned for {instrument} from Binance")
    return [
        Candle(
            timestamp=k.open_time,
            open=float(k.open),
            high=float(k.high),
            low=float(k.low),
            close=float(k.close),
            volume=k.trades,
            timeframe=tf,
            instrument=instrument,
        )
        for k in klines
    ]


def _binance_m1_range(client: BinanceKlineClient, instrument: str, start: datetime, end: datetime) -> list[Candle]:
    return [
        Candle(
            timestamp=k.open_time,
            open=float(k.open),
            high=float(k.high),
            low=float(k.low),
            close=float(k.close),
            volume=k.trades,
            timeframe=Timeframe.M1,
            instrument=instrument,
        )
        for page in client.iter_range(instrument, "M1", start, end)
        for k in page
    ]


def _console_alert(payload: dict, _token) -> bool:
    """fcm_sender stand-in for --feed binance: print the alert notify_node
    would push, so the HUMAN_IN_LOOP path is visible end to end."""
    print("\n[ALERT] " + json.dumps(payload, indent=2, default=str))
    return True


def _serialize_candles_by_tf(candles_by_tf: dict[Timeframe, list[Candle]]) -> dict:
    """Serialise the already-fetched candle window onto the agent message.

    Without this, observe_node's own candles_by_tf parse (message.get(
    "candles_by_tf")) finds nothing, re-derives liquidity_map=None, and the
    grade-gated visual-model/AlgoRAG calls in analyse_node never fire even
    though this function already graded a real setup off real candles —
    exactly the gap noted when this runner was first wired up.
    """
    return {
        tf.value: [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        for tf, candles in candles_by_tf.items()
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeframe",
        default=StrategyConfig().entry_tf.value,
        choices=sorted(tf.value for tf in ENTRY_TIMEFRAMES),
        help=(
            "Entry timeframe to grade setups on — M15 and below only; "
            f"D1/W1/{'/'.join(tf.value for tf in StrategyConfig().context_tfs)} are always pulled too as "
            "HTF bias/context but never drive entry-array selection "
            "(see setup_grader._ENTRY_ELIGIBLE_TIMEFRAMES)."
        ),
    )
    parser.add_argument(
        "--feed",
        default="mt5",
        choices=sorted(DEFAULT_INSTRUMENTS),
        help="Candle source: the local MT5 terminal, or Binance spot crypto (24/7). Default: %(default)s.",
    )
    parser.add_argument(
        "--broker",
        choices=("mt5", "paper", "none"),
        default=None,
        help="What an approved setup becomes: mt5 demo orders, paper-simulated fills, or none "
        "(HUMAN_IN_LOOP console alert). Default: mt5 for --feed mt5, paper for --feed binance.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Re-evaluate at every entry-timeframe bar close instead of a single pass.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="With --loop: stop after this many minutes (default: run until Ctrl+C).",
    )
    parser.add_argument(
        "--paper-state",
        default=str(_PAPER_STATE),
        help="JSON file paper trades persist to (default: %(default)s).",
    )
    parser.add_argument(
        "--store-candles",
        action="store_true",
        help="Upsert every fetched candle into TimescaleDB (TIMESCALE_URL) so the candles table stays current.",
    )
    parser.add_argument(
        "--heartbeat",
        default=None,
        help="File to touch after each pass that fetched fresh data (container health check).",
    )
    parser.add_argument(
        "--paper-fee",
        type=float,
        default=None,
        help="Paper fee rate per side, for net R (default: 0.001 = Binance spot for --feed binance, else 0).",
    )
    parser.add_argument(
        "--instruments",
        default=None,
        help="Comma-separated instrument list to evaluate in one pass (default per feed: "
        + "; ".join(f"{feed}: {','.join(syms)}" for feed, syms in DEFAULT_INSTRUMENTS.items())
        + ").",
    )
    parser.add_argument(
        "--min-rr",
        type=float,
        default=StrategyConfig().min_rr,
        help="Minimum reward:risk to act on a graded setup, regardless of letter grade (default: %(default)s).",
    )
    return parser.parse_args()


def _process_instrument(
    instrument: str,
    fetch: Callable[[Timeframe], list[Candle]],
    graph: AgentGraph,
    cfg: StrategyConfig,
    mode: str,
    verbose: bool = True,
) -> dict:
    """Fetch, grade, and (if warranted) trade one instrument. Returns a
    summary dict for the end-of-run table — never raises for a NO_TRADE
    outcome, only for real fetch/connectivity failures."""
    context_tf_labels = "/".join(tf.value for tf in cfg.context_tfs)
    logger.info("Fetching D1/W1/%s/%s candles for %s...", context_tf_labels, cfg.entry_tf.value, instrument)
    candles_by_tf = {tf: fetch(tf) for tf in cfg.timeframes}

    now = datetime.now(tz=timezone.utc)
    liquidity_map = LiquidityMappingEngine().analyze(candles_by_tf, instrument, now)
    if verbose:
        print("\n" + liquidity_map.to_agent_context() + "\n")

    intent = build_order_intent(liquidity_map, candles_by_tf, instrument, now, cfg)
    if isinstance(intent, NoTrade):
        if intent.reason == "RR_BELOW_MIN":
            print(f"[{instrument}] Graded {intent.grade} but {intent.detail} — skipping.")
            return {"instrument": instrument, "grade": intent.grade,
                    "decision": f"SKIP (R:R {intent.r_ratio:.2f} < {cfg.min_rr})", "trade_id": None}
        if verbose:
            print(f"[{instrument}] No valid setup right now — {intent.detail}")
        return {"instrument": instrument, "grade": "NO_TRADE", "decision": None, "trade_id": None}

    # The candle window rides along so observe_node can run the AI layers.
    message = {**intent.to_message(mode), "candles_by_tf": _serialize_candles_by_tf(candles_by_tf)}

    print(f"[{instrument}] Setup graded {intent.grade.value} — {intent.direction}")
    print(
        f"  entry={intent.entry}  stop_loss={intent.stop_loss}  take_profit_1={intent.take_profit_1}"
        f"  take_profit_2={intent.take_profit_2}  r_ratio={intent.r_ratio:.2f}"
    )
    print(f"  time_window={intent.time_features.time_window} (killzone={intent.time_features.is_killzone})")
    print(f"[{instrument}] Handing off to AgentGraph (mode={mode})...\n")

    final_state = graph.run(message)

    print(f"[{instrument}] decision={final_state.decision}  reason={final_state.decision_reason}")
    if final_state.error:
        print(f"[{instrument}] error: {final_state.error}")

    return {
        "instrument": instrument,
        "grade": intent.grade.value,
        "decision": final_state.decision.value if final_state.decision else None,
        "trade_id": final_state.trade_id,
    }


def _stop_on_sigterm(_signum, _frame) -> None:
    # `docker stop` sends SIGTERM, which Python ignores as a container's PID 1:
    # end the loop the same way Ctrl+C does, so the paper report still prints.
    raise KeyboardInterrupt


def main() -> None:
    args = _parse_args()
    signal.signal(signal.SIGTERM, _stop_on_sigterm)
    cfg = StrategyConfig(entry_tf=args.timeframe, min_rr=args.min_rr)
    instruments = (
        [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
        if args.instruments
        else DEFAULT_INSTRUMENTS[args.feed]
    )
    broker = args.broker or ("mt5" if args.feed == "mt5" else "paper")
    if args.feed == "binance" and broker == "mt5":
        raise SystemExit("--broker mt5 can't trade Binance symbols — use --broker paper or none")

    if args.feed == "mt5" and mt5 is None:
        raise SystemExit("MetaTrader5 isn't installed here (Windows only) — use --feed binance")

    if args.feed == "binance":
        client = BinanceKlineClient()
        fetcher = lambda instrument: (lambda tf: _fetch_binance_candles(client, instrument, tf, cfg.candle_counts[tf]))
        fetch_m1_range = lambda instrument, start, end: _binance_m1_range(client, instrument, start, end)
    else:
        fetcher, fetch_m1_range = _connect_mt5(instruments, cfg.candle_counts)

    store = None
    if args.store_candles:
        timescale_url = config("TIMESCALE_URL", default="")
        if not timescale_url:
            raise SystemExit("--store-candles needs TIMESCALE_URL")
        store = CandleStore(timescale_url, source=args.feed)

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    risk_engine = RiskEngine(redis_client)

    paper = None
    fcm_sender, mode = None, "AUTONOMOUS"
    if broker == "mt5":
        broker_client = _mt5_broker_client()
    elif broker == "paper":
        fee = args.paper_fee if args.paper_fee is not None else (0.001 if args.feed == "binance" else 0.0)
        # Free the risk engine's concurrent-trades slot whenever a paper
        # trade closes or a pending order expires.
        paper = PaperBrokerAdapter(
            args.paper_state, fee_rate=fee, on_close=lambda _trade: risk_engine.decrement_open_trades(_USER_ID)
        )
        broker_client = paper
    else:
        broker_client, fcm_sender, mode = None, _console_alert, "HUMAN_IN_LOOP"

    # Paper trades still active from an earlier run count against the limit.
    open_trades = sum(1 for t in paper.trades() if t["status"] in ("PENDING", "OPEN")) if paper else 0
    redis_client.set(
        f"risk:exposure:{_USER_ID}",
        json.dumps({"daily_dd_pct": 0.0, "weekly_dd_pct": 0.0, "open_trades": open_trades, "equity": _DEMO_EQUITY}),
    )

    graph = AgentGraph(
        redis_client=redis_client,
        risk_engine=risk_engine,
        fcm_sender=fcm_sender,
        broker_client=broker_client,
        trade_journal_collection=_InMemoryJournal(),
        user_id=_USER_ID,
        visual_model_client=VisualModelClient(base_url=_VISUAL_MODEL_URL),
        algorag_client=AlgoRAGSyncClient(base_url=_ALGORAG_URL),
    )

    print(
        f"Evaluating {len(instruments)} instrument(s) from {args.feed} on {cfg.entry_tf.value} "
        f"(broker {broker}, mode {mode}, min R:R {cfg.min_rr}): {', '.join(instruments)}\n"
    )

    # Last M1 bar each instrument's paper trades were advanced through.
    paper_synced: dict[str, datetime] = {}

    def run_pass() -> list[dict]:
        results = []
        fetched: list[Candle] = []
        for n, instrument in enumerate(instruments):
            try:
                base_fetch = fetcher(instrument)

                def fetch(tf: Timeframe) -> list[Candle]:
                    candles = base_fetch(tf)
                    fetched.extend(candles)
                    return candles

                if paper is not None:
                    m1 = fetch(Timeframe.M1)
                    active = paper.active_trade(instrument)
                    if active is not None and m1:
                        # After downtime longer than the M1 window, replay the
                        # missed bars so no fill/stop/target is skipped.
                        synced = paper_synced.get(instrument) or datetime.fromisoformat(active["placed_at"])
                        if synced < m1[0].timestamp:
                            logger.info("[%s] catching paper trade up from %s", instrument, synced)
                            missed = fetch_m1_range(instrument, synced, m1[0].timestamp)
                            fetched.extend(missed)
                            m1 = missed + m1
                    for event in paper.update(instrument, m1):
                        _print_paper_event(event)
                    if m1:
                        paper_synced[instrument] = m1[-1].timestamp
                    active = paper.active_trade(instrument)
                    if active is not None:
                        results.append({"instrument": instrument, "grade": "-",
                                        "decision": f"IN TRADE ({active['status']})", "trade_id": active["trade_id"]})
                        continue
                results.append(
                    _process_instrument(instrument, fetch, graph, cfg, mode, verbose=not args.loop)
                )
            except _FEED_DOWN as exc:
                logger.error("Feed unavailable (%s) — skipping the rest of this pass", exc)
                results.extend(
                    {"instrument": i, "grade": "ERROR", "decision": "feed unavailable", "trade_id": None}
                    for i in instruments[n:]
                )
                break
            except Exception as exc:
                logger.error("[%s] failed: %s", instrument, exc)
                results.append({"instrument": instrument, "grade": "ERROR", "decision": str(exc), "trade_id": None})

        if store is not None:
            store.write(fetched)
        if args.heartbeat and any(r["grade"] != "ERROR" for r in results):
            Path(args.heartbeat).parent.mkdir(parents=True, exist_ok=True)
            Path(args.heartbeat).write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        return results

    try:
        if not args.loop:
            _print_summary(run_pass())
        else:
            deadline = time.monotonic() + args.duration * 60 if args.duration else None
            period = _ENTRY_TF_SECONDS[cfg.entry_tf]
            while True:
                results = run_pass()
                print(
                    f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC  "
                    + "  ".join(f"{r['instrument']}={r['grade']}/{r['decision']}" for r in results),
                    flush=True,
                )
                # Next pass just after the next entry-timeframe bar closes.
                wait = period - time.time() % period + 5
                if deadline is not None and time.monotonic() + wait > deadline:
                    break
                time.sleep(wait)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if args.feed == "mt5" and mt5 is not None:
            mt5.shutdown()
        if paper is not None:
            print("\n=== Paper trades =============================================")
            print(paper.report())
            print(f"(saved to {args.paper_state})")


def _print_summary(results: list[dict]) -> None:
    print("\n=== Summary ==================================================")
    print(f"{'instrument':<10} {'grade':<10} {'decision':<25} trade_id")
    for r in results:
        print(f"{r['instrument']:<10} {r['grade']:<10} {str(r['decision']):<25} {r['trade_id'] or ''}")


def _print_paper_event(event: dict) -> None:
    line = (
        f"[{event['instrument']}] PAPER {event['event']}: {event['direction']} entry {event['entry']} "
        f"stop {event['stop_loss']} target {event['take_profit']}"
    )
    if event["status"] == "CLOSED" and event["gross_r"] is not None:
        line += f" -> {event['gross_r']:+.2f}R gross / {event['net_r']:+.2f}R net"
    print(line, flush=True)


def _mt5_credentials() -> dict:
    credentials = {
        "login": config("MT5_LOGIN", cast=int),
        "password": config("MT5_PASSWORD"),
        "server": config("MT5_SERVER"),
    }
    mt5_path = config("MT5_PATH", default="") or None
    if mt5_path:
        credentials["path"] = mt5_path
    return credentials


def _mt5_broker_client():
    return create_broker_client(
        "mt5",
        **{"path": None, **_mt5_credentials()},
        symbol_suffix=config("MT5_SYMBOL_SUFFIX", default=""),
    )


def _connect_mt5(instruments: list[str], candle_counts: dict[Timeframe, int]):
    """Attach to the local MT5 terminal; return (per-instrument candle
    fetcher factory, M1 range fetcher for paper catch-up)."""
    symbol_suffix = config("MT5_SYMBOL_SUFFIX", default="")

    logger.info("Connecting to MT5...")
    if not mt5.initialize(**_mt5_credentials()):
        code, desc = mt5.last_error()
        raise RuntimeError(f"MT5 initialize failed ({code}): {desc}")

    # Fail fast on a wrong MT5_SERVER_TIMEZONE rather than grade setups off
    # candles shifted by hours (sessions/killzones/daily open all depend on it).
    ticks = [mt5.symbol_info_tick(f"{i}{symbol_suffix}") for i in instruments if mt5.symbol_select(f"{i}{symbol_suffix}", True)]
    _SERVER_CLOCK.check([t.time for t in ticks if t is not None and t.time], datetime.now(timezone.utc))

    def fetcher(instrument: str) -> Callable[[Timeframe], list[Candle]]:
        symbol = f"{instrument}{symbol_suffix}"
        mt5.symbol_select(symbol, True)
        return lambda tf: _fetch_candles(symbol, tf, instrument, candle_counts[tf])

    def m1_range(instrument: str, start: datetime, end: datetime) -> list[Candle]:
        symbol = f"{instrument}{symbol_suffix}"
        candles: list[Candle] = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=20), end)
            rates = mt5.copy_rates_range(
                symbol, mt5.TIMEFRAME_M1, _SERVER_CLOCK.to_server(cursor), _SERVER_CLOCK.to_server(chunk_end)
            )
            for r in rates if rates is not None else []:
                ts = _SERVER_CLOCK.to_utc(r["time"])
                if cursor <= ts < chunk_end:
                    candles.append(Candle(
                        timestamp=ts, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                        close=float(r["close"]), volume=int(r["tick_volume"]), timeframe=Timeframe.M1,
                        instrument=instrument,
                    ))
            cursor = chunk_end
        return candles

    return fetcher, m1_range


if __name__ == "__main__":
    main()
