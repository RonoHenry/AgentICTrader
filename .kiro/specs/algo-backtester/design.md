# Design Document

**Spec**: AlgoBacktester
**Requirements**: `.kiro/specs/algo-backtester/requirements.md` 

## Overview

AlgoBacktester replays M1 history through the live decision path and simulates the resulting orders with a conservative, cost-aware fill model. Its correctness rests on three design choices:

1. **Shared code, not copies.** Each piece of logic that both live and backtest need moves into one module that both import:
   - the as-of candle view
   - the setup-to-order logic
   - the fill model
   - instrument specs

   The backtester then drives the real `AgentGraph` (decide → execute) against a simulated broker, so risk gating, confidence floors and execution guards are the live ones.
2. **Two phases.** Phase A, signal generation, is pure and depends only on candles, so it runs per instrument, in parallel, and is cacheable. Phase B, account simulation, is stateful and runs once, in strict time order across all instruments. It applies the rules that span the whole account: one trade per instrument, concurrent-trade limit and drawdown.
3. **Time is injected everywhere.** Nothing on the decision or fill path reads the wall clock during a backtest. Every component that today calls `datetime.now()` on that path takes a clock.

### Changes to existing live code

These are deliberate, small, and each is covered by its own task:

| # | Change | Why | Requirement |
|---|---|---|---|
| L1 | Extract setup-to-order logic from `scripts/run_live_agent.py` into `agent/order_intent.py`, and its constants into `agent/strategy_config.py` | One implementation for live and backtest | 1.2, 1.6 |
| L2 | `setup_id` becomes deterministic, derived from the entry PD array's id (new `SetupGradeDetail.entry_array_id`) instead of `uuid4()` | Re-grading the same array yields the same id: needed for D6 (one attempt per setup) and for duplicate-order protection | 1.3, D6 |
| L3 | Live runner builds its candle window with `compose_as_of_view()`: closed entry-TF bars, and HTF bars on the strategy calendar (aggregated from H1 where the broker's native bars follow a different clock) | Live evaluates exactly what the backtest replays, at any broker | 2.7, D5, D9 |
| L4 | `PaperBrokerAdapter` delegates fills to `agent/brokers/fill_model.py` and takes an injectable clock | One fill model; parity with backtests | 4.1, 4.2, D4 |
| L5 | `AgentGraph`, `observe_node`, `learn_node` and `log_agent_decision` accept a clock (default: wall clock) | `observe_node`'s 60-second staleness check reads `datetime.now()` and would reject every replayed setup | 2.5 |
| L6 | `scripts/load_historical_data_mt5.py` stores each bar's spread, in price units | Cost model | 3.5, 5.1 |
| L7 | Delete `ml/backtesting/engine.py` and `backend/tests/test_backtesting_engine.py` | Superseded | — |
| L8 | Broker profiles: `agent/broker_profiles.py` + `config/brokers/<profile>.toml`. The spec export script and MT5 history loader take `--profile` | Any broker without code changes; credentials stay in `.env` | 10 |

---

## Architecture

```mermaid
flowchart TB
    subgraph Data["Data (per instrument)"]
        DB[(TimescaleDB candles<br/>M1 + native HTF warm-up)]
        SRC[CandleSource]
        AGG[HTF aggregation<br/>StrategyCalendar]
        DB --> SRC --> AGG
    end

    subgraph PhaseA["Phase A: signals (parallel per instrument, cacheable)"]
        VIEW[compose_as_of_view<br/>shared with live]
        ENG[LiquidityMappingEngine.analyze]
        OI[build_order_intent<br/>shared with live]
        AGG --> VIEW --> ENG --> OI
        OI --> SIG[(SignalRecords)]
    end

    subgraph PhaseB["Phase B: account simulation (one pass, time-ordered)"]
        LOOP[EventLoop<br/>merges M1 bars + signals]
        ACC[SimAccount<br/>equity, drawdown anchors]
        GRAPH[AgentGraph decide → execute<br/>clock = simulated t, AI clients off]
        RISK[RiskEngine.validate<br/>fakeredis exposure from SimAccount]
        SB[SimBroker : BrokerClient]
        FM[FillModel<br/>shared with PaperBroker]
        SIG --> LOOP
        AGG --> LOOP
        LOOP --> GRAPH --> RISK
        GRAPH --> SB --> FM
        LOOP --> SB
        SB --> ACC --> RISK
    end

    subgraph Out["Outputs: data/backtests/run_id/"]
        MAN[manifest.json]
        JRN[journal.csv]
        SUM[summary.json + summary.md]
    end
    LOOP --> JRN
    ACC --> SUM
    LOOP --> MAN
```

### Package layout

```
agent/
  order_intent.py          # NEW (L1): build_order_intent(), OrderIntent, NoTrade
  strategy_config.py       # NEW (L1): StrategyConfig (windows, min R:R, grade→confidence, expiry rule)
  instruments.py           # NEW: InstrumentSpec, tick value conversion, spec loading
  broker_profiles.py       # NEW (L8): BrokerProfile, credential resolution from .env, symbol map
  brokers/fill_model.py    # NEW (L4): FillModel, Bar, SimOrder, FillEvent
  brokers/paper.py         # CHANGED (L4): delegates to FillModel, injectable clock
  graph.py, nodes/*.py     # CHANGED (L5): clock injection
services/market_data/
  strategy_calendar.py     # NEW: StrategyCalendar — New York-close period boundaries per TF (D9)
  as_of_view.py            # NEW (L3): aggregate(), compose_as_of_view()
config/
  brokers/<profile>.toml   # NEW (L8): venue, credential env-var names, server clock, symbol map, spec file
  instruments/<profile>.toml  # per-broker specs + costs, exported (e.g. exness-standard.toml, binance.toml)
  backtests/base.toml      # NEW: base run configuration + named variants
algo_backtester/           # NEW package (backtest-only; not shipped in the paper-trader image)
  config.py                # RunConfig, StudyConfig, variant resolution
  data.py                  # CandleSource (TimescaleSource, CsvSource), coverage check, fingerprint
  signals.py               # Phase A
  cache.py                 # Phase A cache
  sim_broker.py            # SimBroker(BrokerClient): sizing, costs, FillModel
  account.py               # SimAccount: equity, drawdown anchors, exposure for RiskEngine
  simulation.py            # Phase B event loop
  run.py                   # hold-out guard, Phase A once, Phase B per (walk-forward) window (task 204)
  metrics.py               # summary statistics, bootstrap CI, breakdowns
  report.py                # manifest / journal / summary writers
  compare.py               # side-by-side comparison of runs
  report_html.py           # self-contained HTML run report (Req 11)
  cli.py, __main__.py      # CLI: run | compare | check-data (task 208)
scripts/
  export_instrument_specs.py    # NEW: venue specs + measured costs → config/instruments/<profile>.toml
  export_forward_test_fixture.py # NEW: forward-test period → parity fixture
  run_fx_forward_test.ps1        # NEW: Exness FX/gold paper forward test on the Windows host (Req 9.6)
```

Tests follow the existing convention for engine and agent code: `backend/tests/test_backtest_*.py`, with fixtures under `backend/tests/fixtures/backtester/`. `data/backtests/` is added to `.gitignore`.

---

## Components and Interfaces

### StrategyCalendar (`services/market_data/strategy_calendar.py`)

Defines where every strategy candle starts, the same for all brokers and venues (D9, Req 3.3). The engine therefore sees identical candles whether the data came from a UTC server, a New York-close server or Binance.

```python
class StrategyCalendar:
    def period_start(self, t: datetime, tf: Timeframe) -> datetime: ...   # UTC in, UTC out
    def period_end(self, t: datetime, tf: Timeframe) -> datetime: ...
    def matches_native(self, clock: MT5ServerClock | None, tf: Timeframe) -> bool: ...
```

- Floor the instant in **New York wall time shifted by +7 h**, then convert back to UTC. This is the same rule as an MT5 `ny_close` server clock, so DST is handled by `zoneinfo`.
  - D1 starts at 17:00 New York.
  - W1 starts at Saturday 17:00 New York: the `ny_close` server's Sunday 00:00, the label MT5 gives weekly bars. The FX week (Sunday 17:00 open to Friday 17:00 close) falls inside it.
  - On US DST-change days, boundaries map to their first real occurrence. A period running into New York's repeated hour absorbs it, so periods tile time with no gaps or overlaps, which matters for crypto.
  - H1–H12 floor to multiples of their length from the 17:00 day start. H3, H4, H6, H8 and H12 all divide 24 hours, so they nest inside D1. H4 starts at 17:00, 21:00, 01:00, 05:00, 09:00 and 13:00 New York.
- `matches_native` reports where a venue's native bars can be used directly:
  - every TF for an MT5 `ny_close` server;
  - H1 and below for a whole-hour UTC offset (e.g. Exness, UTC+0) and for Binance.

### As-of view (`services/market_data/as_of_view.py`)

```python
def aggregate(bars: Sequence[Candle], tf: Timeframe, calendar: StrategyCalendar) -> list[Candle]:
    """Closed-period OHLCV bars of `tf` built from finer bars (M1 in backtests)."""

def compose_as_of_view(
    closed: Mapping[Timeframe, Sequence[Candle]],  # closed bars per TF, oldest first
    recent_m1: Sequence[Candle],                   # M1 bars covering the largest in-progress HTF period
    t: datetime,
    entry_tf: Timeframe,
    windows: Mapping[Timeframe, int],              # StrategyConfig.candle_counts
    calendar: StrategyCalendar,
) -> dict[Timeframe, list[Candle]]:
```

Rules, matching Req 2.1–2.4:
- A bar is *closed at t* when `bar.timestamp + duration(tf) <= t`. This uses M1 close times, never open times.
- **Entry timeframe and below:** the last `windows[tf]` closed bars.
- **Higher timeframes:** the last `windows[tf] - 1` closed bars, plus one in-progress bar. The in-progress bar is aggregated from `recent_m1` bars that start at or after `calendar.period_start(t, tf)` and closed at or before `t`. If no such M1 bar exists yet, there is no in-progress bar and the window holds `windows[tf]` closed bars.
- The function is pure: no I/O and no clock.

**How each side supplies its inputs:**
- **Backtest:** `closed` comes from `aggregate()` over stored M1. Where M1 history starts after the warm-up a window needs (W1 × 30 is about 30 weeks), it falls back to the stored native HTF bars, and the manifest records the warm-up source per TF.
- **Live (L3):** for each TF where `calendar.matches_native(...)`, `closed` is the venue's native bars with the forming bar dropped. Other TFs are aggregated from native H1 bars (D1 × 90 needs about 2,200 H1 bars; W1 × 30 about 5,000). `recent_m1` is fetched to cover the current W1 period (about 7,200 M1 bars at most: one MT5 call, or 8 Binance requests).
- **Equivalence:** the aggregation-parity test (Req 3.4) is what makes native and aggregated closed bars interchangeable wherever `matches_native` is true.

### StrategyConfig (`agent/strategy_config.py`)

A frozen Pydantic model that holds what is now scattered through `run_live_agent.py`:
- `entry_tf` and `context_tfs` (H12, H8, H6, H4, H3)
- `candle_counts` (today's `_CANDLE_COUNT`)
- `min_rr` (default 3.0)
- `grade_confidence` (A+ 0.90, A 0.80, B 0.70)
- `tp_levels` (2.5, 4.0)
- `pending_expiry`: `KILLZONE_END` or `FIXED_TTL`, with `fallback_ttl_minutes` 180 (the TTL under `FIXED_TTL`, and outside every killzone under `KILLZONE_END`)

`fingerprint()` hashes the model's canonical JSON. Grader parameters stay in `liquidity_engine` and enter the manifest through the engine code fingerprint.

### Order intent (`agent/order_intent.py`)

```python
@dataclass(frozen=True)
class OrderIntent:
    setup_id: str; instrument: str; entry_tf: Timeframe; as_of: datetime
    grade: SetupGrade; direction: Literal["LONG", "SHORT"]
    entry: float; stop_loss: float; take_profit_1: float; take_profit_2: float | None
    r_ratio: float; confidence: float
    time_features: TimeFeatures; patterns: tuple[dict, ...]; regime: str
    def to_message(self, mode: AgentMode) -> dict: ...   # the AgentGraph message the runner builds today

@dataclass(frozen=True)
class NoTrade:
    instrument: str; as_of: datetime; grade: str; reason: str   # NO_GRADE | NO_TRADE | RR_BELOW_MIN
    detail: str = ""; r_ratio: float | None = None              # grader's reason / R:R shortfall, for logs and the journal

def build_order_intent(liquidity_map, view, instrument, as_of, cfg: StrategyConfig) -> OrderIntent | NoTrade:
```

It is a move of `_process_instrument` lines 447–509 with behaviour unchanged, apart from the deterministic `setup_id` (L2):

```python
setup_id = deterministic_id("setup", instrument, cfg.entry_tf.value, grade_detail.entry_array_id)
```

Both the live runner and Phase A call this function, so Req 1.3 holds by construction. A test also asserts it by running the refactored runner path and Phase A on the same fixture view.

`to_message()` omits `candles_by_tf`. Without it, `observe_node` doesn't run the engine a second time. That second run is redundant today (the runner already analysed), and the AI layers that consume its output are disabled in backtests anyway.

`to_message(mode, detected_at=None)` stamps `detected_at`, which `observe_node`'s 60 s staleness check measures from. It defaults to `as_of`: a backtest detects at t. Live, data is as of the last bar close but detection happens when the runner evaluates, so the runner passes the hand-off time.

### InstrumentSpec (`agent/instruments.py`, `config/instruments/*.toml`)

```python
@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str; venue: Literal["mt5", "binance"]
    point: float; tick_size: float; contract_size: float
    volume_min: float; volume_step: float; volume_max: float
    base_ccy: str; quote_ccy: str
    default_spread: float                  # price units: typical spread, floors each bar's recorded spread (Req 5.1, D10)
    commission: CommissionSpec             # PER_LOT_PER_SIDE (MT5) | RATE_PER_SIDE (Binance, 0.001)
    stop_slippage: float                   # D3 amended, price units: 25% of default_spread, min 2 points; crypto 0.05% of export-time price

def money_per_price_unit(spec, price: float, conversion: float | None, account_ccy="USD") -> float:
```

- Value of a one-price-unit move for one lot, in account currency:
  - quote = USD: `contract_size`
  - base = USD (USDJPY, USDCAD): `contract_size / price`
  - crosses: multiply by `conversion`, the quote→USD rate at that time, taken from the conversion pair's M1 series. That pair must be present in the store, or the run refuses the instrument (Req 3.6 coverage check).
- `scripts/export_instrument_specs.py` writes one spec file per broker profile. Three rules:
  - **Commission (D2):** total `|commission| + |fee|` over recent deals ÷ total traded volume. This is correct whether the broker splits commission across entry and exit or charges the round trip on entry.
  - **Typical spread:** median ask − bid over 72 h of ticks.
  - **Refusal:** it writes nothing while a value is missing or zero, or while our money-per-tick disagrees with the broker's `trade_tick_value`.

### BrokerProfile (`agent/broker_profiles.py`, `config/brokers/<profile>.toml`)

```toml
# config/brokers/exness-standard.toml
venue = "mt5"
spec_file = "config/instruments/exness-standard.toml"
server_clock = "+0"                 # verified against live ticks on connect (Req 10.6)
[credentials]                        # names of .env variables, never values (Req 10.2)
login = "MT5_LOGIN"
password = "MT5_PASSWORD"
server = "MT5_SERVER"
[symbols]                            # instrument -> broker symbol
EURUSD = "EURUSDm"
XAUUSD = "XAUUSDm"
```

`load_profile(name)` returns the venue, the resolved credentials (read from the environment at call time), an `MT5ServerClock`, the symbol map and the `InstrumentSpecs`. Instruments missing from `[symbols]` map to themselves. The export script and MT5 history loader take `--profile` (Req 10.5).

A profile without `spec_file` is **data-only**: a candle source that is never priced or traded. `metaquotes-demo` is one, the New York-close reference server for the aggregation-parity test (task 186), since that demo reports zero spreads. `connect_mt5(profile, attach=True)` uses the account the terminal is already logged into instead of logging in; the clock check still runs, and it is what confirms the terminal is on that broker.

### FillModel (`agent/brokers/fill_model.py`)

A pure state machine shared by `PaperBrokerAdapter` and `SimBroker` (Req 4.1).

```python
@dataclass(frozen=True)
class Bar:            # one M1 bar; prices are BID (MT5 convention)
    timestamp: datetime; open: float; high: float; low: float; close: float
    spread: float     # price units, max(recorded, spec.default_spread) (Req 5.1); ask = bid + spread

@dataclass
class SimOrder:
    order_id: str; setup_id: str; instrument: str; direction: Literal["LONG", "SHORT"]
    kind: Literal["MARKET", "LIMIT"]; entry: float; stop: float; target: float | None
    placed_at: datetime; expires_at: datetime | None
    status: Literal["PENDING", "OPEN", "CLOSED"]
    ideal_fill: float | None; fill: float | None          # ideal = before spread/slippage
    ideal_exit: float | None; exit: float | None; exit_reason: str | None
    filled_at: datetime | None; closed_at: datetime | None
    mae_price: float | None; mfe_price: float | None

class FillModel:
    def __init__(self, stop_slippage: float): ...   # price units, from InstrumentSpec.stop_slippage
    def step(self, order: SimOrder, bar: Bar) -> list[FillEvent]:   # mutates order; returns FILLED/SL/TP/EXPIRED/REJECTED events
```

Rules, implementing Req 4. Throughout, `ask = bid + spread`.

| Rule | Behaviour |
|---|---|
| Eligibility | Only bars with `timestamp >= placed_at` are considered. |
| Market entry (4.3) | Fills at the next bar's open: ask for LONG, bid for SHORT. `ideal_fill` = bid open. |
| Limit entry (4.4) | LONG fills when `low + spread < entry`, at `entry`. SHORT fills when `high > entry`, at `entry`. Strict inequality: a touch is not a fill. |
| Expiry (4.10) | PENDING and `bar.timestamp >= expires_at` gives EXPIRED. No bars exist while the venue is closed, so nothing fills then (4.11), and an order expiring over a weekend expires on the first bar after reopening. |
| Stop (4.5–4.7) | LONG triggers when bid `low <= stop`. SHORT triggers when ask `high + spread >= stop`. Exit price is `stop`, or the bar open if the bar opened beyond the stop (gap), then worsened by `stop_slippage`. |
| Target (4.5) | LONG exits when bid `high >= target`. SHORT exits when ask `low + spread <= target`. Exit at `target`, no slippage (it is a resting limit). |
| Same bar (4.8) | Stop and target both reachable: stop wins. |
| Fill bar (4.9) | On the bar a limit fills, a stop-out may occur; a target exit may not. |
| Excursions (4.12) | `mae_price` / `mfe_price` update on every bar while OPEN, using the side that would close the position: bid for LONG, ask for SHORT. |
| Invalid stops | A MARKET order whose fill price is already beyond its stop or target is REJECTED (`INVALID_STOPS`), as a broker rejects invalid stops. |

Settled while building it (task 194):
- **Ideal vs actual prices.** `ideal_fill` / `ideal_exit` are the bid at that moment, before slippage; `fill` / `exit` are on the executing side (ask for buys) plus slippage. A trade pays the spread once, on its buy: a LONG limit fills at `entry` with `ideal_fill = entry - spread`; a SHORT stop exits at `stop` with `ideal_exit = stop - spread`. Gross R uses ideal prices, net R actual ones.
- **Fill bar.** Req 4.9 applies to LIMIT fills. A MARKET fill happens at the open, before the rest of the bar, so a target on that bar counts (the same-bar rule still applies). A stop on a limit's fill bar exits at the stop, never at the open: the position didn't exist at the open.
- **Excursions.** They start from the closing-side price at the fill. A limit's fill bar counts only its adverse extreme (the favourable one may predate the fill), and an exit caps the excursion at the exit's market price.
- **Killzone end.** Killzones include their end, so an order placed at that instant (e.g. t = 10:00 New York, an M15 close) expires at once.

**Expiry rule `KILLZONE_END`:** `expires_at` is the end of the killzone containing `placed_at`, using `liquidity_engine.utils.time_utils.KILLZONE_WINDOWS`. If `placed_at` falls outside every killzone, `expires_at = placed_at + fallback_ttl` (3h, today's paper default). The expiry time is computed when the order is placed, by the broker (paper or sim), from `StrategyConfig.pending_expiry`.

**PaperBroker after L4:**
- Builds `Bar` objects from its candles. Binance klines carry no spread, so it uses the instrument's `default_spread`.
- Gets its clock from the constructor.
- Keeps its public API, report and JSON state, and adds the new fields.
- Its old `fee_rate` maps onto `CommissionSpec.RATE_PER_SIDE`.
- `update()` takes closed bars only and processes each bar once (`processed_through` per trade); the runner drops the forming M1 bar.
- Its placement time is the clock at hand-off, a few seconds after t, so a paper MARKET order fills at the open of the M1 bar after that, one minute later than a backtest placing at t. The forward-test parity check (task 212) should expect that for market entries.

### SimBroker (`algo_backtester/sim_broker.py`)

A `BrokerClient` that `execute_node` calls through `AgentGraph`, exactly as live code calls the paper or MT5 broker.

- `place_order(order)` mirrors `MT5BrokerAdapter`:
  - **Order type:** LIMIT if the entry is on the discount/premium side of the current price, else MARKET.
  - **Sizing:** `lots = risk_amount / (|entry - stop| × money_per_price_unit)`, rounded **down** to `volume_step`.
  - **Minimum volume:** if `volume_min × |entry - stop| × money_per_price_unit > risk_amount × (1 + 0.10)`, it raises `SimBrokerError("MIN_VOLUME_OVER_RISK")`. `execute_node` already turns broker exceptions into `decision=SKIP`, and the journal records the reason (Req 6.2).
  - **Missing fields:** a missing `direction`, `stop_loss` or `risk_amount` raises (`INVALID_ORDER`), rather than defaulting.
  - **Invalid stops:** a stop or target on the wrong side of the limit price (or of the market fill, for a market order) raises `SimBrokerError("INVALID_STOPS")`, as MT5's `order_send` refuses it. `build_order_intent`'s draw-on-liquidity fallback target can land behind the entry, and its R:R check uses `abs()`, so this happens.
  - **Order ids:** sequential (`sim-000001`), not random (Req 9.5).
- `advance(instrument, bar)` steps every active order for that instrument through `FillModel` and returns the orders that closed, as `ClosedTrade`s; Phase B books them into `SimAccount`. The bar is also the market price for orders placed at its close.
- `active_trade(instrument)` supports the one-trade-per-instrument rule, as `PaperBrokerAdapter.active_trade` does live.

**R accounting for a closed trade** (Req 4.12, 5.3):
- `initial_risk = |entry - stop|`: the distance the order was sized on (the limit price, or a market order's requested entry). R is therefore money in units of the risk budget.
- `gross_r = direction × (ideal_exit - ideal_fill) / initial_risk`
- `net_r = direction × (exit - fill) / initial_risk - commission_r`
- `commission_r = commission_money / (lots × initial_risk × money_per_price_unit)`
- `cost_r = gross_r - net_r`, reported split into its spread (the buy side's bar spread), slippage (`stop_slippage` on SL exits) and commission components, each `>= 0`.
- `mae_r` / `mfe_r = direction × (excursion_price - fill) / initial_risk`, on the closing side.

*Changed in task 201* from `initial_risk = |ideal_fill - stop|`, which the paper broker also uses. For a LONG limit `ideal_fill = entry - spread`, so with this strategy's stops that definition breaks:
- it reaches zero or goes negative when the spread is as wide as the stop. The first real EURUSD intent (task 217) had a 0.6-pip stop against Exness's 0.8-pip spread;
- it inflates LONG results (a 2.6-pip stop with a 0.8-pip spread loses about -1.44 "R" for about 1× the risk budget in money);
- it differs between a LONG and its mirror-image SHORT.

`PaperBrokerAdapter._r_multiples` still uses the old definition. It must move to this one before the parity check (task 212).

### SimAccount (`algo_backtester/account.py`)

- **Equity:** with `compounding = false` (the default, Req 6.4), `risk_amount = initial_equity × risk_per_trade` and stays fixed. Equity still moves, for drawdown purposes.
- **Drawdown anchors (Req 6.3):** at 17:00 New York, the start-of-day equity anchor is reset. The weekly anchor resets at the Sunday open.
  - The boundaries are the strategy calendar's D1 and W1 periods. W1 starts Saturday 17:00 New York, and the FX week opens inside it, so for FX the weekly anchor is the Sunday open.
  - An anchor is the last mark of the period before. A mark at exactly 17:00 (the bar closing then) still belongs to the old day.
  - `daily_dd_pct = max(0, (day_anchor - equity_mark) / day_anchor × 100)`, where `equity_mark` includes open positions marked at the bar close (`SimBroker.open_pnl()`, closing side, before commission). The weekly figure is computed the same way.
- **Exposure:** `exposure()` returns the dict `RiskEngine` reads from `risk:exposure:{user_id}`. Phase B writes it to the run's fakeredis before every `AgentGraph.run()` (Req 1.4).
  - `RiskEngine` sizes at a fixed 1% (`RISK_PER_TRADE`) of the `equity` it reads, so `exposure()["equity"] = risk_amount / RISK_PER_TRADE`. That way the run's `risk_per_trade` and non-compounding budget reach `execute_node`'s `risk_amount`. At the default 1%, without compounding, it is the starting equity.

### Phase A: signal generation (`algo_backtester/signals.py`)

```python
@dataclass(frozen=True)
class SignalRecord:
    t: datetime; instrument: str
    result: OrderIntent | NoTrade | EngineError      # EngineError: analyze() raised (kept, counted)
    context: TradeContext | None = None              # set for OrderIntents; drawn by the run report (Req 11.5)

@dataclass(frozen=True)
class TradeContext:   # compact extract of the LiquidityMap at t — not the whole map; JSON-ready values
    entry_array: dict | None        # type, direction, timeframe, high, low, formed_at
    draw_on_liquidity: dict | None  # type (BSL/SSL), source, price, formed_at
    swept_level: dict | None        # price and time of the opposite-side raid, once the grader records it
    killzone: str | None            # liquidity_engine time_utils windows (as KILLZONE_END expiry); None outside

def generate_signals(instrument, source, calendar, cfg, start, end) -> Iterator[SignalRecord]:
```

For every entry-TF close `t` in `[start, end]` with data:

```
view = compose_as_of_view(...)
liquidity_map = LiquidityMappingEngine().analyze(view, instrument, t)
record build_order_intent(liquidity_map, view, instrument, t, cfg)
```

- **Incremental windows:** aggregated series and window indices advance with `t`; nothing is re-sliced from scratch per step.
- **Parallelism:** one process per instrument (`ProcessPoolExecutor`). Each worker writes its records to the cache.

**Cache (`algo_backtester/cache.py`, Req 7.4)**
- **Key:** `sha256(data_fingerprint[instrument], engine_code_fingerprint, StrategyConfig minus execution-only fields, instrument, start, end)`.
  - `pending_expiry` and `fallback_ttl_minutes` are left out: only the fill model reads them, so an expiry variant reuses Phase A (Req 7.4). Every other field counts, including any added later.
- **Storage:** `data/backtests/cache/<key>.jsonl`, one JSON line per `SignalRecord`, then a trailer with the key, the record count and a sha256 of the record lines.
  - Written to a temporary file and then renamed, so a crash never leaves a half-written cache entry.
  - An entry that fails the trailer check is deleted and recomputed.
- **Engine code fingerprint:** a sha256 over the paths and contents (line endings normalised) of `cache.ENGINE_SOURCES`. Any edit to analysis or order logic therefore invalidates the cache automatically. Besides `liquidity_engine/**/*.py`, `agent/order_intent.py` and `agent/strategy_config.py`, the list covers the code that shapes what the engine sees or what a record holds: `as_of_view.py`, `strategy_calendar.py`, `mt5_clock.py`, `algo_backtester/data.py` (warm-up), `algo_backtester/signals.py` (the record format) and `session_features.py` (an intent's time features). A listed file that goes missing raises, so a rename can't silently drop it.
- **Invariant:** a cache hit and a fresh run give identical Phase B input.

**Measured performance (task 181, 2026-10-05).** `analyze()` was timed on the live runner's exact windows (`_CANDLE_COUNT`), 200 calls each:

| Window | p50 | p95 | Phase A per instrument-year |
|---|---|---|---|
| EURUSD, entry M15 | 50 ms | 172 ms | ≈ 21 min |
| EURUSD, entry M5 | 62 ms | 105 ms | ≈ 78 min |
| BTCUSDT, entry M15 | 51 ms | 92 ms | ≈ 30 min |
| BTCUSDT, entry M5 | 225 ms | 333 ms | ≈ 6.6 h |

What this means:
- **M15 studies are practical as-is,** with instruments running in parallel.
- **M5 crypto is not.** Cost depends on the data, not only on window size: the BTCUSDT M5 window produced 1,835 PD arrays per call.
- **Profile (cProfile, BTCUSDT M5):**
  - `candle_utils.calculate_atr` is called about 1,038 times per `analyze()` from `PDArrayDetector._detect_order_blocks`. It recomputes ATR per candle, which is quadratic in window length, and accounts for about 40% of the time.
  - `_detect_bpr` compares fair value gaps pairwise: about 15%.
  - Swing-structure classification: about 18%.
- Task 214 removes these hot spots without changing outputs.

**After task 214 (2026-10-05).** Measured on the frozen fixture windows (`backend/tests/fixtures/backtester/engine_windows/`), best p50 of three interleaved rounds against the pre-change engine, with output asserted byte-identical on every run:

| Window | Before | After | Speed-up | Phase A per instrument-year (after) |
|---|---|---|---|---|
| BTCUSDT, entry M5 | 132.7 ms | 77.7 ms | 1.7× | ≈ 2.3 h |
| BTCUSDT, entry M15 | 90.2 ms | 56.4 ms | 1.6× | ≈ 33 min |
| EURUSD, entry M15 | 89.7 ms | 51.1 ms | 1.8× | ≈ 21 min |
| EURUSD, entry M5 | 112.3 ms | 61.0 ms | 1.8× | ≈ 76 min |

What changed:
- **ATR:** `PDArrayDetector._detect_order_blocks` now uses `atr_series()`: the same true ranges summed in the same order, so values are exactly equal, once per timeframe.
- **Swing structure:** `SwingStructureClassifier` memoises `_break_confirmed` for the duration of one `classify()` call.

What did not change:
- **BPR detection.** The planned sort-and-sweep was not applied. Its pairing loop is cheap; its cost is building BPR outputs that must remain.
- **`deterministic_id` (uuid5), about 26%.** IDs are content hashes, so a different hash would change outputs.

Remaining options for long M5 studies:
- the Phase A cache;
- per-instrument parallelism;
- memoising `deterministic_id` across consecutive bars, whose windows overlap about 99%. Evaluate in task 199. A same-window benchmark would overstate that gain.

**Phase A measured (task 199, 2026-10-06).** With the live defaults (M15 entries, full windows), real MetaQuotes EURUSD/XAUUSD data: about 33 ms per entry close including the as-of view, so about 14 min per instrument-year. Not worth memoising `deterministic_id` for M15 studies; revisit for long M5 studies.

### Phase B: account simulation (`algo_backtester/simulation.py`)

One `AgentGraph` per run:
- `risk_engine = RiskEngine(fakeredis)`, `broker_client = SimBroker`, `mode = AUTONOMOUS`
- `visual_model_client = None`, `algorag_client = None`
- `clock = lambda: sim_now`
- `trade_journal_collection = None` and `agent_decisions_collection = None` (*changed in task 203* from list-backed collections). `learn_node` queues an MLflow retraining run every 50 journal documents, which a year of decisions would trigger dozens of times. Phase B's own journal records every decision instead.

The event loop runs over the merged, time-ordered stream of M1 bars (all instruments) and SignalRecords. For each minute boundary `t`:

1. **Advance positions.** For every instrument with an M1 bar closing at `t` (alphabetical order, for determinism), call `sim_broker.advance(bar)`, then `account.mark(bar)`.
2. **Act on signals.** For each SignalRecord with time `t` (alphabetical order):
   - If it is `NoTrade` or `EngineError`, write a journal row.
   - If `sim_broker.active_trade(instrument)` exists, write a journal row with reason `IN_TRADE`. Live runs skip evaluation in this case.
   - If the `setup_id` has already been attempted, write a journal row with reason `SETUP_ALREADY_ATTEMPTED` (D6).
   - Otherwise write `account.exposure()` to fakeredis, set `sim_now = t`, call `graph.run(intent.to_message(AUTONOMOUS))`, and journal the final state: decision, reason and `order_id`.
3. **Exposure.** Account-wide rules (concurrent trades, drawdown) see the true state because step 1 completes for every instrument before any step 2 at the same `t` (Req 7.5).

**Ordering and look-ahead:**
- Ordering matches live: fills and exits first, then evaluation.
- An order placed at `t` is only eligible for bars with `timestamp >= t`, i.e. bars that open after the decision, so there is no same-bar look-ahead.

Settled while building it (task 203):
- **Attempted (D6)** means the broker accepted an order for the `setup_id`, whatever became of it (filled, stopped, expired). A setup refused by the risk rules or the broker (e.g. `MIN_VOLUME_OVER_RISK`) is evaluated again on the next close, as live.
- **Exposure is current at every decision:** the account is marked again before each `graph.run()`, so orders placed earlier at the same `t` count towards the concurrent-trade limit. `RiskEngine.increment_open_trades` writes to the same key, but Phase B overwrites it from the account each time.
- **Output:** `SimulationResult(journal, trades, open_orders, account)`. Each `JournalRow` carries its intent, `TradeContext`, `time_window` and, once it closed, its `ClosedTrade`. An order still open at the end is reported in `open_orders`, not closed artificially.

**Walk-forward (Req 7.3):** `run --walk-forward 3M` splits `[start, end)` into consecutive windows. Each window is a full Phase B run, with warm-up data taken from before the window start (Phase A records are shared through the cache). The combined result concatenates the windows' trades.
- *As built (task 204, `algo_backtester/run.py`):* Phase A runs once over the whole range. A signal at `t` depends only on data up to `t`, so each window's decisions equal a per-window Phase A with warm-up from before its start. Each window then gets its own account and broker. Windows step by `D`, `W` or `M`, counted from the run start; month steps clamp to month ends.
- The bar closing at a window's start is passed with it, to price the first decision. An order open at a window's end stays in that window's `open_orders`.
- `run_backtest()` refuses a cross before any work: its quote currency needs a conversion rate over time, which isn't supported yet.

**Hold-out (Req 7.2):** `StudyConfig` in `config/backtests/studies/<study>.toml` sets `holdout_start` once (a subdirectory, so a study can't overwrite a run config such as `base.toml`). Its default is D7: the most recent 3 months at study creation. A run whose `[start, end)` overlaps the hold-out is refused unless `--final` is passed, and the manifest records `final_validation: true`.

---

### Run report (`algo_backtester/report_html.py`, Req 11)

```python
def write_report_inputs(run_dir, journal, candles, entry_tf, bars_before=60, bars_after=20) -> None:  # context.json, candles.json
def write_html_report(run_dir: Path) -> Path:                                                       # from the run dir alone
def build_forward_test(trades, candles, entry_tf, source) -> dict;  render(model) -> str
```

- **One file:** `report.html` holds a JSON data block and a small inline script that draws each chart as SVG when its row is selected. There are no `http(s)` references, so it works offline (Req 11.1).
  - *As built (task 218):* the design embedded plotly.js. Its bundle is 4.8 MB per report, and the hand-drawn SVG covers Req 11.5; zoom and hover are what plotly would add.
  - The data is compacted: empty fields are dropped, and repeated reasons and contexts are stored once. A two-day, one-instrument report is about 100 KB.
- **Data:** the run directory's own files (Req 11.6):
  - `journal.csv` and `manifest.json`;
  - `context.json`: each order intent's `TradeContext`, written by `run`;
  - `candles.json`: the entry-TF candles cut from the run's fingerprinted data around its decisions, with the window lengths (`[report] chart_bars_before` / `chart_bars_after`).
  - `python -m algo_backtester report <run_dir>` regenerates the page byte-identically from these files.
- **Chart:**
  - entry-timeframe candles;
  - horizontal lines for entry, stop and target, from the decision until the exit or expiry;
  - markers for decision, fill and exit;
  - the entry PD array as a shaded box, the draw on liquidity as a dashed line, the swept level when present;
  - the killzone as a background band.
- **Forward test:** `report --forward-test <trades.json> --profile <p>` reads the paper broker's trade file, aggregates entry-TF candles from the store's M1, and renders the same explorer (Req 11.7). Paper trades have no recorded context, and their R is as the paper broker computed it.

### FX paper forward test (`scripts/run_fx_forward_test.ps1`, Req 9.6)

Runs `scripts/run_live_agent.py --profile exness-standard --feed mt5 --broker paper --loop` on the Windows host, because MetaTrader5's Python API is Windows-only and can't run in the Linux paper-trader container.
- Paper state goes to `data/paper_trades_fx.json` and logs to `data/fx_forward_test.log`.
- A Task Scheduler entry (documented, created by the user) restarts it at logon.
- It needs the live runner to support `--profile` (task 192) and the paper broker on the shared fill model (task 195), so its trades are valid parity data from day one.

## Data Models

### Run configuration (`config/backtests/base.toml`)

```toml
[run]
profile = "exness-standard"                              # D11: venue, specs, costs, symbols
instruments = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]   # D1
start = "2025-01-01"
end = "2026-07-01"
study = "baseline-2026q3"

[account]
initial_equity = 10000.0
risk_per_trade = 0.01
compounding = false

[strategy]            # → StrategyConfig
entry_tf = "M15"
min_rr = 3.0
pending_expiry = "KILLZONE_END"
fallback_ttl_minutes = 180

[data]
max_gap_minutes = 30          # outside weekends/holidays (Req 3.6)
allow_gaps = false

[report]
min_trades = 30               # D8
cost_flag_fraction = 0.25     # Req 5.5
bootstrap_resamples = 10000

[variants.min_rr_5]
strategy.min_rr = 5.0
```

A variant is a dotted-key override of the base. The CLI takes `--variant min_rr_5`.

### Run manifest (`manifest.json`)

- **Identity:** `run_id` is the sha256 of the canonical manifest content, excluding `created_at`. Identical manifests therefore produce the same id and the same outputs (Req 9.5).
- **Fields:**
  - `git_commit`, `git_dirty`
  - `engine_code_fingerprint`, `strategy_config` (full), `run_config` (resolved, variant applied)
  - `variant`, `study`, `final_validation`
  - `data`: per instrument `{start, end, m1_rows, sha256, warmup_source_by_tf, default_spread_bars}`
  - `broker_profile` and `instrument_spec_source` (the spec file's `# Source:` line, Req 10.3)
  - `instrument_specs` (resolved)
  - `ai_modifiers: "disabled"`, `news_filter: "not_applied"` (Non-Goals)
  - `bootstrap_seed`, derived from `run_id`
  - `created_at`, the only non-deterministic field

### Journal (`journal.csv`), one row per SignalRecord that reached Phase B

The columns:
- **Identity:** `t`, `instrument`, `setup_id`, `grade`
- **Decision:** `decision` (`NO_TRADE` / `RR_BELOW_MIN` / `IN_TRADE` / `SETUP_ALREADY_ATTEMPTED` / `SKIP` / `EXECUTE` / `ENGINE_ERROR`), `reason`
- **Setup levels:** `direction`, `entry`, `stop`, `target`, `r_ratio`, `confidence`
- **Order lifecycle:** `order_id`, `order_kind`, `placed_at`, `expires_at`, `filled_at`, `fill`, `ideal_fill`, `closed_at`, `exit`, `ideal_exit`, `exit_reason`
- **Size:** `lots`
- **Results:** `gross_r`, `net_r`, `cost_r_spread`, `cost_r_slippage`, `cost_r_commission`, `mae_r`, `mfe_r`, `holding_minutes`
- **Flags:** `cost_flag` (Req 5.5)

Floats are written with fixed precision and rows are sorted by `(t, instrument)`, so identical runs produce byte-identical files.

### Summary (`summary.json`, `summary.md`)

- **Overall figures (Req 8.2):** trade count, win rate, average gross/net R, expectancy net R with bootstrap 95% CI, profit factor, max drawdown (R and %), longest losing streak, average holding time, cost share of gross R.
- **Breakdowns (Req 8.3):** by instrument, grade, killzone (from `time_window`), direction and month.
- **Evidence flag (Req 8.4):** every bucket with `n < min_trades` carries `"evidence": "insufficient"`, and `summary.md` renders those buckets greyed and labelled.

---

## Correctness Properties

Each property is checked with Hypothesis over generated inputs: random-walk M1 series, random orders and random bar sequences. The truncation property instead uses fixture data, because `analyze()` is slow.

### Property 1: No Look-Ahead (Truncation Invariance)

*For any* instrument series and any entry-TF close `t` within it, the SignalRecord produced at `t` from the full series SHALL equal the SignalRecord produced at `t` from the series truncated to M1 bars closed at or before `t`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

---

### Property 2: As-of View Contains Only Known Data

*For any* `t`, every bar `compose_as_of_view()` returns for the entry TF and below SHALL have `timestamp + duration(tf) <= t`. Each HTF window SHALL contain at most one bar whose period has not ended, and that bar SHALL be built only from M1 bars closed at or before `t`.

**Validates: Requirements 2.1, 2.2, 2.3**

---

### Property 3: Aggregation Consistency

*For any* M1 series, `aggregate(aggregate(m1, H1), D1)` SHALL equal `aggregate(m1, D1)`. For every aggregated bar, `low <= min(open, close)` and `max(open, close) <= high` SHALL hold.

**Validates: Requirements 3.3**

---

### Property 4: No Fill Before Placement or After Expiry

*For any* order and bar sequence, bars with `timestamp < placed_at` SHALL NOT change the order's state. A pending order SHALL NOT fill on any bar with `timestamp >= expires_at`.

**Validates: Requirements 4.3, 4.10**

---

### Property 5: Fills Are Never Better Than the Order's Levels

*For any* order and bar sequence:
- a LONG limit fill price SHALL be `<= entry`, and a SHORT limit fill `>= entry`;
- a stop exit SHALL be at or beyond the stop: `<= stop` for LONG, `>= stop` for SHORT;
- when one bar reaches both stop and target, the exit reason SHALL be `SL`.

**Validates: Requirements 4.4, 4.5, 4.6, 4.7, 4.8**

---

### Property 6: Costs Only Subtract

*For any* closed trade, `cost_r_spread`, `cost_r_slippage` and `cost_r_commission` SHALL each be `>= 0`, and `net_r <= gross_r`.

**Validates: Requirements 5.3**

---

### Property 7: Loss Is Bounded by the Stop Unless Price Gapped

*For any* closed trade whose stop-out bar did not open beyond the stop, `gross_r >= -1`. Only a gap can produce a loss larger than the planned risk.

**Validates: Requirements 4.6**

---

### Property 8: Sizing Never Over-Risks

*For any* accepted order:
- `lots` SHALL be a whole multiple of `volume_step` within `[volume_min, volume_max]`;
- `lots × |entry - stop| × money_per_price_unit` SHALL be `<= risk_amount × 1.10`.

**Validates: Requirements 6.1, 6.2**

---

### Property 9: Account State Matches Positions

*For any* point in a simulation:
- `SimAccount.exposure()["open_trades"]` SHALL equal the number of PENDING or OPEN orders;
- `daily_dd_pct` and `weekly_dd_pct` SHALL be `>= 0`;
- no instrument SHALL have more than one PENDING or OPEN order.

**Validates: Requirements 1.4, 1.5, 6.3**

---

### Property 10: Determinism and Cache Transparency

*For any* run configuration:
- two runs with identical manifests SHALL produce byte-identical `journal.csv` and `summary.json`;
- a run served from the Phase A cache SHALL produce the same outputs as a run with an empty cache.

**Validates: Requirements 7.4, 9.5**

---

## Error Handling

| Condition | Behaviour |
|---|---|
| Coverage gap or late history start (Req 3.6) | `check-data` and `run` stop before Phase A with a per-instrument report, unless `allow_gaps = true`. That flag is recorded in the manifest. |
| Missing instrument spec or conversion pair | Refuse that instrument; refuse the run if any requested instrument is refused. |
| `analyze()` raises at some `t` | Record `EngineError`, continue, and report the count. The run fails if errors exceed 1% of evaluations, since that indicates a systematic problem. |
| `SimBroker` rejects an order (min volume, missing fields) | `execute_node` records SKIP with the reason, and the journal keeps it. |
| Stale or corrupt cache entry | The key includes all inputs, so a mismatch can't hit. A corrupt file is deleted and recomputed. |
| Hold-out overlap without `--final` | Refuse with a message naming the hold-out range. |
| `compare` across different data ranges or fingerprints | Refuse (Req 8.5). |

---

## Testing Strategy

The tests follow the TDD steering doc: each task is written RED first. They live at `backend/tests/test_backtest_*.py` unless noted.

| Test | Covers | Kind |
|---|---|---|
| `test_backtest_fill_model.py` | Every row of the FillModel table, using hand-built bars: gap, same-bar, fill-bar, weekend expiry, spread side conventions, MAE/MFE | Unit (Req 4, 9.1) |
| `test_backtest_strategy_calendar.py` | New York-close boundaries for every TF across DST changes; `matches_native` for `ny_close`, UTC+0 and Binance | Unit (Req 3.3) |
| `test_backtest_broker_profiles.py` | Profile loading, credentials resolved from env vars (never stored), symbol map, clock mismatch refused | Unit (Req 10) |
| `test_backtest_aggregation_parity.py` | Aggregated M1 equals native bars within one tick: H1 and below vs Exness and Binance; H4/D1/W1 vs a `ny_close` server (MetaQuotes-Demo, as test data) | Fixture (Req 3.4) |
| `test_backtest_as_of_view.py` | Closed-bar rules, in-progress HTF bar, window sizes | Unit (Req 2.1–2.4) |
| `test_backtest_truncation.py` | Hypothesis picks `t` in a fixture series. `generate_signals` on data cut at `t` equals the record at `t` from the full series. Capped at `max_examples=25` because `analyze()` is slow. | Property (Req 2.6, 9.2) |
| `test_backtest_order_intent_parity.py` | Refactored runner path and Phase A give the same `OrderIntent` for the same view; `setup_id` is stable across consecutive bars for the same entry array | Unit (Req 1.3, L2) |
| `test_backtest_sim_broker.py` | Sizing per instrument class (USD quote, USD base, cross), rounding down, `MIN_VOLUME_OVER_RISK`, R and cost accounting | Unit (Req 5, 6.1–6.2) |
| `test_backtest_account.py` | Drawdown anchors at 17:00 New York (including DST), exposure dict consumed by `RiskEngine.validate()` | Unit (Req 6.3, 1.4) |
| `test_backtest_metrics.py` | Statistics on known trade lists, seeded bootstrap determinism, insufficient-evidence flag, compare refusal | Unit (Req 8) |
| `test_backtest_report_html.py` | Report is offline (no external references), contains every journal row, chart windows and markers are correct, context drawn only from recorded data, forward-test input accepted | Unit (Req 11) |
| `test_backtest_golden.py` | End-to-end run on `fixtures/backtester/golden/`: two weeks of EURUSD M1 plus a native-HTF warm-up, journal equal to the committed expected file; a second run is byte-identical | Golden (Req 9.4, 9.5) |
| `test_backtest_parity.py` | Replays the forward-test fixture and matches its trades | Fixture (Req 9.3) |
| `test_paper_broker.py` (existing, updated) | PaperBroker behaviour on the shared FillModel, plus the clock injection | Unit (L4) |

**Parity timing.** The parity fixture can only exist once the forward test has run on the shared FillModel (L4). Trades from before the switch were filled with the old optimistic rules and can't match. Task order is therefore: L4, then let the forward test accumulate trades, then export the fixture with `scripts/export_forward_test_fixture.py`, then the parity test. Until the fixture exists, the test is not written. It is never written as skipped.

---

## Update 2026-10-16: Noculus

Requirements 17–20; decisions D27 to D30. The server side lives in `algo_backtester/noculus.py`, used by `watch.py`; the page is `engine.html`/`engine.js` with a `noculus.js` layer, served by the charts app.

### Blind sessions (`watch.py`)

- **Starting blind:** `WatchSession(..., blind=True)`.
- **While blind:** `state_at(w)` returns only the clock, the journal shows no orders or trades, and `candidates` is empty.
- **Reveal:** `reveal(w)` records the reveal time and stops withholding. Everything up to `w` is then shown, and play continues as usual.
- **Why on the server:** the page can't leak what the server never sends.

### Marks (`noculus.py`)

- **`mark(tool, tf, clicked, clock)`** reads the session's bars of `tf` that closed by `clock`.
  - **FVG:** C3 is the clicked candle and C1 the candle two before. It needs a gap. The gap and CE come from `algo_research.atlas.arrays.fvgs`, so research and Noculus define it once.
  - **IFVG:** the same, plus a later close beyond the far edge by `clock`. Direction is flipped.
  - **OB:** the clicked candle's range and its body midpoint (MT). Direction defaults to opposite the candle's colour; the trader may set it.
  - **Breaker:** the same, plus a later close beyond the block by `clock`. Direction is flipped.
- **A refusal** names its reason: no gap, not closed by the clock, no close beyond the edge yet.
- **The journal** (`data/journal/noculus/<instrument>/<session>.json`) holds `marks`, `trades`, `reveal` and `comparison`. It is written atomically after each change.

### Pseudo trades (`noculus.py`)

- **Placing:** `place(direction, kind, entry, stop, target, expiry, mark_id, clock)`.
- **Settling:** at any clock, `settle(clock)` runs every open trade with `algo_research.races.run_races` over the M1 bars before the clock. A limit fills at the first bar that trades through its price before its expiry, and its race starts there.
- **Manual exit:** `close(trade_id, clock)` exits at the last M1 close by the clock, on the closing side.
- **Costs** come from the session's broker-profile spec, as the backtest's do.

### The comparison (`noculus.py`, `cli.py`)

- **Arrays:** the engine's arrays of each marked timeframe, as the session kept them at the reveal clock, are matched to the trader's marks by (family, timeframe, direction, formation candle within one bar). Unmatched ones on either side are listed with their zones.
- **Trades:** the engine's journal and the trader's trades, grouped by trading date. Pairs share a direction and day; the gap between their fill times is shown.
- **The report:** `python -m algo_backtester noculus` reads every journal into `data/journal/noculus/REPORT.md`.

## Requirement Traceability

| Requirement | Design element |
|---|---|
| 1 Same decision code | L1, L2, `build_order_intent`, Phase B through `AgentGraph` + `RiskEngine`, `StrategyConfig` |
| 2 No look-ahead | `compose_as_of_view`, closed-bar rule, clock injection (L5), truncation test, L3 |
| 3 Data and aggregation | `StrategyCalendar`, `aggregate`, `CandleSource`, coverage check, fingerprint, L6 |
| 4 Fill model | `FillModel`, `KILLZONE_END` expiry, L4 |
| 5 Costs | `InstrumentSpec`, `CommissionSpec`, spread floor on `Bar`, R accounting, `cost_flag` |
| 6 Sizing and account | `SimBroker` sizing, `SimAccount` |
| 7 Run modes | `RunConfig` variants, `StudyConfig` hold-out, walk-forward, Phase A cache, two-phase parallelism |
| 8 Reporting | `report.py`, `metrics.py`, `compare.py` |
| 9 Self-validation | Testing Strategy table |
| 10 Broker profiles | `BrokerProfile`, `config/brokers/*.toml`, L8, manifest `broker_profile` |
| 11 Run report | `report_html.py`, `TradeContext` on `SignalRecord` |
| 9.6 FX forward test | `scripts/run_fx_forward_test.ps1`, runner `--profile` (task 192), paper broker on `FillModel` (L4) |
| 13 TradingView overlay | `pine.py`, the `pine` command (update 2026-10f) |
| 14 Failure modes in the report | `report_html.py` reads `autopsy.csv` (update 2026-10f) |

---

## Update 2026-10f: The Engine on the Trader's Own Charts

### `algo_backtester/pine.py` (Requirement 13)

```python
MAX_TRADES = 120                                      # D26

class PineError(Exception): ...                       # an empty or too-large window

def pine_script(run_dir: Path, instrument: str, start: date, end: date,
                cfg: Optional[NarrativeConfig] = None) -> str
def write_pine(run_dir: Path, instrument: str, start: date, end: date,
               cfg: Optional[NarrativeConfig] = None) -> Path   # <run_dir>/pine/<instrument>_<start>_<end>.pine
```

**Inputs.** Everything comes from the run directory:
- `load_run`, `autopsy_table` (task 291);
- the journal's `t` and `grade`;
- each setup's swept level and draw in `context.json`;
- the D1 narrative of `candles.json` on the narrative's price basis.

**Which trades.** The window holds the instrument's filled, closed trades whose decision falls on a trading date in `[start, end]`.

**The script.** A fixed Pine v6 template:
- `indicator(..., overlay = true, max_boxes_count = 500, max_lines_count = 500, max_labels_count = 500)`;
- the inputs of Requirement 13.5;
- the data as typed `var array<...> = array.from(...)` literals, sorted by decision time:
  - times are UNIX milliseconds, which `xloc.bar_time` reads, so the chart's time zone doesn't matter;
  - floats always carry a decimal point, so Pine infers the type;
  - a missing raid or draw is 0 (a sentinel);
  - strings are escaped;
  - long literals wrap with a 6-space continuation indent (any indent that isn't a multiple of 4).

**Each bar** (D25):
1. Create the D1 opens whose day starts before `time_close`.
2. Open the trades whose decision time is before `time_close`:
   - risk and reward boxes from the decision to the current bar;
   - the decision label;
   - the raided pool's line (formed → raided, both at or before the decision);
   - the draw's line.
3. For each open trade:
   - put a fill marker on the bar holding its fill;
   - extend its boxes and draw line to `time_close`;
   - on the bar holding its exit, end them at the exit, add the exit label, and drop it from the open list.

The open list is walked from the end, guarded against an empty list, because a Pine `for` loop from −1 to 0 still runs.

**Symbol check.** On the last bar, a label warns when `syminfo.ticker` doesn't contain the instrument.

**CLI.** `python -m algo_backtester pine <run_dir> --instrument EURUSD (--month 2025-03 | --start 2025-03-01 --end 2025-03-31) [--config narrative.toml]`
- exit 0 when written;
- exit 2 when the run can't be read or the window is refused.

### `report_html.py` (Requirement 14)

`build_from_run_dir` reads `autopsy.csv` when present and maps `setup_id` → mode onto each filled trade's row:
- the row gains `mode`;
- `mode` joins `_FILTERS`;
- the details panel shows it.

Without the file, rows carry no `mode` and the filter is absent, so older runs and the golden report render unchanged.

---

## Update 2026-10-19: The Fractal + POI Indicator (Requirements 21–23)

Decisions D31–D35. The port is `algo_research/fractal_poi/`. Noculus serves it from `watch.py` and paints it with `static/fractal.js`.

### The port (`algo_research/fractal_poi/`)

| Module | Pine source | What it holds |
|---|---|---|
| `frames.py` | `getHigherTF` … `getFractalHTF`, `getAutoHTF2`, `fvg_get_htf_period`, `lq_f_bsl_auto_tf`, `ValidTimeframe`, the Quarterly sessions | the HTF for a chart; `starts(wall, tf)` and `period_end(start, tf)` for every timeframe the indicator uses, on the charts' clock |
| `chart.py` | — | `Chart`: the chart's candles aggregated from M1 as Noculus aggregates them, with their close times; `Now`, the clock's candle; Pine's box, line and label as plain data |
| `settings.py` | the inputs | `FractalSettings` with the indicator's defaults; `DRAW_ONLY`, the inputs that only choose what is drawn |
| `model.py` | `Monitor`, `Update`, `ICUpdate`, `CheckSMTDivergence`, `DrawAll`, `DrawSetups`, `DrawHTF2` | HTF candles and setups: C1–C4, CISD, IC-CISD, zones, SD, formation liquidity, SMT |
| `liquidity.py` | `f_lq_*`, `f_prev_level`, `f_bsl_mini`, `f_bsl_ssl_v2`, the swings, `f_rc_*` | the liquidity suite |
| `imbalance.py` | the FVG engine, `fvg_detect` | HTF fair value gaps |
| `__init__.py` | the main execution | `FractalPOI`, the reader; `PARTNERS` (D34), `partners_for`, `warmup_days`, `defaults` |

**Reading.** `FractalPOI.at(clock)` reads each chart candle once it has closed by the clock (`Chart.closed_by`). Each candle is read in the script's own order: the liquidity suite, the FVG engine, the SMT trackers, `Monitor`, `Update`, then HTF2. The reader then draws what the script draws on its last bar, taking the clock's candle (`Chart.now`: the candle holding the last M1 closed by the clock) as that bar:
- the HTF candles sit `offset` candles to its right;
- lines that run "to now" end on it;
- an entry zone runs to its close, until the zone's own end.

**Positions.** Pine counts some positions in bars (`bar_index`). A bar already read takes its own open time. A bar not yet read (a position ahead of price) is counted in chart candles from the clock's candle. So no time comes from a candle the clock hasn't reached, and the page's own logical mapping places it where TradingView would.

**State.** Pine's `na` is NaN for prices, so comparisons with it are false in both. For bar indexes it is None.
- Forward is incremental: one candle per step.
- Going back restores the nearest checkpoint, taken every 250 candles. Checkpoints share the candle-boundary arrays.

**Warm-up.** `warmup_days(tf, s)`: enough HTF candles for the setups kept, 60 FVG-timeframe candles, 40 candles of each BSL timeframe shown, and the previous week (and the previous month when PM levels are on). At most 120 days.

### On Noculus (`watch.py`, `static/fractal.js`)

- **`WatchSession.fractal(q)`** answers `GET /api/watch/fractal?tf=&t=&s=`, where `s` is the trader's changed inputs as JSON.
  - The candles come from the session's snapshot M1, from the warm-up to the session's end. Partners come from the snapshot too.
  - Up to four readers are kept, by chart timeframe and computing inputs. A drawing input reuses its reader and only redraws.
  - The events are the session's own: from its start, the latest 200.
  - It answers while the session is blind (D33).
- **`GET /api/watch/fractal-defaults`** gives the inputs' defaults, the Fractal modes and `DRAW_ONLY`, for the dialog.
- **`fractal.js`** asks again only when something can have changed:
  - another timeframe or input;
  - the clock reaching the view's `refresh_at` (the clock's candle closing);
  - the clock going back.

  It paints Pine's three objects, with the indicator's black as the theme's ink, and counts the HTF timer down from the clock between fetches. Its panel is the dashboard. Its settings dialog has five tabs (Inputs, Model, HTF, Liquidity, FVG & SMT), and the trader's changes are kept in this browser.

### Property 11: The Indicator Reads Nothing After the Clock

*For any* clock `t`, chart timeframe and inputs, `FractalPOI(data).at(t)` equals `FractalPOI(data truncated to the M1 bars closed by t).at(t)`, partners included.

**Validates: Requirements 22.1, 22.2**

| Requirement | Design element |
|---|---|
| 21 The indicator, ported | `algo_research/fractal_poi/` (D31, D34, D35) |
| 22 Read at the clock | `FractalPOI.at`, `Chart.closed_by`, `Chart.now`, Property 11 (D32) |
| 23 On the chart | `WatchSession.fractal`, the two endpoints, `static/fractal.js` (D33) |

## Update 2026-10-21: Your Position Against the Engine's Trade (Requirements 25–26)

Decisions D37–D39. The server side is in `noculus.py` and `watch.py`; the page adds the tools to `engine.js` and the positions to `noculus.js`.

### Positions (`noculus.py`)

- **`position_ticket(body, path, clock)`** turns a drawing (`direction`, `entry`, `stop`, `target`, `drawing`) into `place`'s ticket (D37). The price at the clock is the last M1 close by it, as `place` reads it. "Near" is two typical spreads (the path's spread floor).
- **Engine ideas.** `engine_ideas(journal, path, clock_end, costs)` reads the backtest's journal rows:
  - an EXECUTE row is an idea from its `placed_at` to its `closed_at`, or its expiry when it never filled. Its outcome, net R and fill are the backtest's; its best R is `mfe_r`;
  - consecutive SKIP rows with the same side, entry and stop are one idea, from the first row's close to one entry candle after the last. It is placed with `place` at the first close as `SimBroker.place` would: a limit at the entry when the entry is better than the price (expiring when the idea ends), else at market. `settle` runs it to the session's end, so it is priced as the trader's trades are. A stop or target already on the wrong side is kept, unpriced, as REFUSED.
- **`idea_at(ideas, clock)`**: the latest idea live at the clock; **`next_idea(ideas, clock)`**: the first idea after it on the same trading day.
- **Scale.** `average_ranges(m1, clock)`: the mean true range of the last 14 M15, H1 and D1 candles closed by the clock, from `aggregate` on the session's snapshot M1, with the D1 candles on the 17:00 clock.
- **`compare_positions(trades, ideas, ranges_at, clock)`** pairs each of the trader's trades placed by the clock (Requirement 26.2), measures both sides (26.3) and labels the pair (D38):
  - *other side*: the directions differ;
  - *scale*: the same side, and the larger stop is at least 2× the smaller, or the larger target distance at least 2× the smaller;
  - *location*: the same side and scale, and the entries are more than the trader's stop distance apart;
  - *agree*: anything else; *none*: no engine idea.

  It returns the pairs and a summary: the labels counted, the side agreement, the medians of the stops and targets in M15 ATR and of the R:Rs, and both net Rs.
- **`write_report`** also reads the journals that hold `positions`, including open sessions' (`*-open.json`), and adds a positions section.

### The session (`watch.py`)

- **Journals.** `WatchApp.start` gives every session a journal. A blind one keeps its name; an open one is `<first day>-<days>d-<variant>-open.json`.
- **`place_position(body)`** places a drawn position at the clock in any session that keeps a journal, and stamps it with `drawing` and `engine_seen` (D39). The ticket (`place`) and the marks stay blind-only: `_still_marking` now also refuses an open session.
- **`engine_ideas`** are built once, after the backtest, from `self.journal`, and served with the journal (`GET /api/watch/journal` → `ideas`). While blind they are withheld, as the rows are.
- **`positions(q)`** (`GET /api/watch/noculus/positions?t=`) settles the trades to the clock, then returns `compare_positions`. While blind and unrevealed, the engine's side of each pair is withheld (26.4). When the engine is in sight, the result is saved in the journal as `positions`.
- **`POST /api/watch/noculus/position`** is `place_position`.

### The page

- **Tools.** `engine.js` adds Long (▲, Alt+L) and Short (▼, Alt+S) to its toolbar; `drawings.js` already draws them.
- **Placing.** Selecting a position drawing shows it in the Noculus panel with "Place at <clock>" (and the same in its context menu). The panel's text says which order it becomes (market, or a limit at the entry).
- **Live.** On each tick, `noculus.js` writes each linked drawing's `status` (waiting, open +0.42R, TARGET +3.56R) and repaints the drawings.
- **The engine's idea.** Under "Orders & trades", a SKIP idea live at the clock is drawn as a dashed position box, labelled "engine wanted … skipped: <reason>".
- **The pairs.** The Noculus panel lists each position beside the engine's idea, with the label and the measures in M15 ATR. It shows in every session; in a blind one, the engine's side reads "hidden until you reveal".

| Requirement | Design element |
|---|---|
| 25 The position tool | `position_ticket`, `WatchSession.place_position`, `POST /api/watch/noculus/position`, the toolbar and panel (D37, D39) |
| 26 The engine's trade beside yours | `engine_ideas`, `idea_at`, `average_ranges`, `compare_positions`, `GET /api/watch/noculus/positions`, the SKIP box, the report (D38) |

## Update 2026-10-22: Live on Noculus (Requirement 27)

Decisions D40–D41. The terminal is read in `live.py`; the session, the app and the charts take it in `watch.py` and `charts.py`; the page follows it in `engine.js`.

- **`live.py`.** `LiveSource(rates, instruments, history=240 days, now)` has the same shape as `SnapshotSource` (`_frame`, `bars`, `last_time`, `held`):
  - an instrument's M1 is read on first use and topped up by `refresh`;
  - other timeframes come straight from `rates`, for a warm-up the M1 doesn't reach;
  - only bars closed by `now` are kept.

  `Terminal(profile)` is the real `rates`. It calls `copy_rates_range` in chunks, on the profile's symbol and server clock, and gives the spread in price. It connects on first use and takes one call at a time.
- **`WatchSession(…, live=source)`.** The session reads `self.source` wherever it read the snapshot: the data, Model A and the indicator. In a live session:
  - `_prepare` first tops up the M1 and sets `end` to the last closed minute. The run reaches to the end of that UTC day but holds nothing after the clock.
  - The engine's record at each close is kept in `_records`, so a refresh reads only the new closes.
  - Phase B runs again over all the closes, with `final` set (D40).
  - The journal is built whole before it is swapped in.
- **`refresh()` / `status()`.** `status()` starts a background `refresh()` when the session is live and ready, and the last refresh began `LIVE_EVERY` (30) seconds ago or more. Refreshes take a lock. `version` counts the refreshes that moved the end.
- **`WatchApp`.**
  - `live=` takes a factory: `live_feed(config)` gives the profile's `Terminal`, or None when the profile isn't MT5. The factory makes one `LiveSource` on the first live start.
  - `start({"live": true, …})` sets the first day with `live_first_day(now, days)`. A live session is kept apart from the replayed ones.
  - `meta()` says whether live is offered.
- **The charts.** `charts.serve` passes the feed. In a live session, `watchlist_for` reads each instrument's last four days of terminal M1 (`ChartsApp._live_bars`).
- **The market now.** `LiveSource.forming(instrument)` is for the chart only. It takes the closed M1 of the last 8 days, then the feed's minutes after them, the forming one included; it keeps nothing. `LiveSource.quote` / `Terminal.quote` give the last tick.

  `WatchSession.live_now(tf)` (`GET /api/watch/live?tf=`) returns:
  - the chart's bars from the one holding the last closed minute, read from `forming` with `ReplayBars.as_of(…, since=)`;
  - the bid and ask;
  - the session's `end` and `version`.

  It also asks for a refresh. That refresh tops up the minutes every `LIVE_EVERY` (5) seconds, and runs `_prepare` only when the source holds a minute past this session's end. Another session on the same market may have topped up the shared source already, so the check is against this session's end, not against the top-up's count.
- **A cross.** When the account's currency is neither of the instrument's, `_prepare` gives the run `InstrumentSpecs(venue, quote_ccy, {instrument: spec})` (D42).
- **The page.** A "Live" box, shown when the server offers it, disables the first day. A live session opens at its end, and `follow()` asks for `/api/watch/live` every second:
  - at the end, it puts the forming bars on the chart, and the header shows `LIVE`, the time, the bid and the ask;
  - when `version` or `end` moves, it reads the status and the orders again, and steps the clock to the new end if the clock was there.

  In a live session the Play button reads "● Live" at the end, and "⏭ Back to live" (which jumps to the end) when stepped back. The speed menu is hidden.

| Requirement | Design element |
|---|---|
| 27 A live session | `live.py` (`LiveSource`, `forming`, `quote`, `Terminal`), `WatchSession(live=…)`, `refresh`, `live_now`, `live_first_day`, `live_feed`, `ChartsApp._live_bars`, the page's `follow()` (D40–D42) |

## Update 2026-10-27: Partials and Break-Even (Requirement 28)

Decisions D43–D45. The rule is set in `config.py`, sized in `sim_broker.py`, executed in `fill_model.py` and drawn by `engine.js`.

- **`ManagementSection`** (`config.py`): `partial_r` (0 is off) and `partial_fraction` (0 < f < 1, default ⅓). `RunConfig.management` defaults to off. Phase A never reads it, and the cache key is built from the StrategyConfig alone, so the cache is untouched (D43).
- **`SimOrder`** (`fill_model.py`) gains the settings `partial_r` and `partial_fraction` (None and 0 are off), and the results `partial_price`, `partial_at` and `partial_ideal_exit`.
  - `_fill` sets `partial_price` to `fill ± partial_r × |fill − stop|`, or None when that is at or beyond the target.
  - `_manage` checks in this order:
    1. the stop (unchanged);
    2. the partial, from the closing-side favourable extreme, not on a limit's fill bar. It records the price, the time and the ideal (bid) price, and moves `order.stop` to `order.fill`. Then it checks the target on the same bar.

    The events are `PARTIAL`, then any `TP`. The paper broker never sets `partial_r`, so it is unaffected.
- **`SimBroker(partial_r=0.0, partial_fraction=0.0)`.** At placement it rounds `lots × fraction` down to the volume step. When the part and the rest both reach `volume_min`, the trade carries the setting and the actual share. Otherwise it carries neither (D44). `advance` records the partial bar's spread.
- **`_closed_trade`.** With f the actual share (0 without a partial):
  - `net_r = sign × [f (partial − fill) + (1 − f)(exit − fill)] / risk − commission − swap`;
  - gross is the same on ideal prices.
  - Spread: LONG `entry_spread`; SHORT `f × partial_spread + (1 − f) × exit_spread`. Slippage: `(1 − f)` of a stop exit's. Commission: per side and price, on the part's and the rest's lots. Swap: each part's lots times its own nights.

  With f = 0, every expression reduces to the old one, so unmanaged journals don't change.
- **`simulate(…, management=)`** passes the section to the broker; `run_backtest` passes `cfg.management`. The watch runs `run_backtest`, so a session of a managed variant is managed.
- **The journal** adds `partial_at`, `partial_exit` and `partial_fraction` after `lots`. The watch's rows carry them, and `engine.js` marks the partial (a dot and "⅓ off +3.0R") and labels a rest stopped at the fill "BE".
- **`focus.toml`** gains `fresh_near_gap_partial`: `fresh_near_gap` plus `management.partial_r = 3.0` and `management.partial_fraction = 1/3`.

| Requirement | Design element |
|---|---|
| 28 A partial, then break-even | `ManagementSection`, `SimOrder.partial_*`, `FillModel._manage`, `SimBroker(partial_r, partial_fraction)`, `_closed_trade`, `simulate(management=)`, the journal's partial columns, `engine.js` (D43–D45) |
