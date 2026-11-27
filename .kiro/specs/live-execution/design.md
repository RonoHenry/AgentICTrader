# Design Document

**spec**: Live Execution: safe orders on the broker

## Overview

The live MT5 path takes the backtester's rules, not new ones. Where the backtester has a rule (sizing, the partial's split, expiry, the account's anchors), the live path calls the same code. Where a live-only guard is needed (the stop backstop), SimBroker gets the same switch, off by default.

```
run_live_agent.py --broker mt5 --config <run> --variant <v>
  every minute:      broker.sync(now)            expire, recompute the part's target, break-even, close out
                     account.sync(now, terminal) balance, equity, anchors
  each entry close:  for each market:
                       IN TRADE / SETUP_ALREADY_ATTEMPTED?  skip
                       exposure <- account (broker truth)   then AgentGraph -> execute_node -> broker.place_order
```

## Components

| Component | File | What changes |
|---|---|---|
| Sizing | `agent/brokers/sizing.py` (new) | `round_down`, `lots_for_risk`, `split_lots`, `stop_overrun`; `SizingError(reason)`. Pure functions. |
| SimBroker | `algo_backtester/sim_broker.py` | `_lots` and `_partial` call the shared functions; optional `max_stop_overrun` (off). Results unchanged. |
| MT5 adapter | `agent/brokers/mt5.py` | Sizes through `sizing`; the backstop; the profile's symbols; expiry; the split; a ledger; `sync`, `active_trade`, `active_count`, `account_snapshot`. |
| Ledger | `agent/brokers/mt5.py` (`MT5Ledger`) | A JSON file of own trades: tickets, setup_id, instrument, prices, expiry, partial state. Written by write-then-rename, like the paper broker's state. |
| Live account | `algo_backtester/account.py` (`LiveAccount`) | A SimAccount whose balance and equity come from the terminal. Same anchors. Persisted. |
| Runner | `scripts/run_live_agent.py` | The profile on MT5, the per-minute sync, exposure before each decision, IN TRADE and attempted on MT5, attempted on paper. |

The Phase A cache is untouched: none of these files is in `ENGINE_SOURCES` (`agent/order_intent.py` and `agent/strategy_config.py` don't change).

## Decisions

Defaults stand until the trader answers.

| # | Decision | Default and why |
|---|---|---|
| LX-D1 | The stop backstop is on live, off in the backtest | Live 0.5: spread plus slippage can't exceed half the stop, so a stop-out costs at most about 1.5 budgets. Off in SimBroker, because turning it on would change every recorded result. The parity test runs both with it on. Trades it refuses live that the backtest took are a known divergence; the variants meant for live already floor the stop at 10 spreads (`min_stop_spreads`), far above it. |
| LX-D2 | The partial is two tickets, not a watched position | The broker fills the part at its exact level, so the partial doesn't depend on the runner being awake. Only the break-even move needs the runner (Requirement 7.3), and it runs every minute. The alternative, polling one position and closing a share, would fill the partial late by up to a minute, at market. |
| LX-D3 | The budget comes from the account, not `[account] initial_equity` | The demo's balance is what is at risk. `initial_equity` stays the backtest's. Without compounding the budget is fixed at the balance of the first start (persisted), as the backtest fixes it at its initial equity. |
| LX-D4 | Broker truth, not counters | Open trades are counted from the terminal each time, instead of incrementing and decrementing a number. A restart, a manual close or an expiry can't make it drift. `execute_node`'s increment stays: the runner overwrites it before the next decision, as `simulate()` does. |
| LX-D5 | Management every minute, evaluation at each entry close | Evaluating every market each minute would refetch every window for nothing. The sync is a handful of terminal calls. |
| LX-D6 | Expiry is sent to the broker when allowed, and enforced by the runner anyway | SPECIFIED expiry works while the runner is down. The runner's cancel covers symbols that only allow GTC. |
| LX-D7 | An order expiring at placement isn't sent | The backtest places it and it expires unfilled: no fill either way. The ledger records it EXPIRED, so the setup counts as attempted (D6) in both. |

## Known divergences (after this spec)

- **Break-even timing.** The backtest moves the rest's stop on the bar the partial fills. Live moves it within the minute after. A reversal inside that minute stops the rest at the original stop.
- **Market fills.** The backtest fills a market order at the next M1 bar's open; live fills at the tick. The partial level follows each one's actual fill (Requirement 7.2).
- **Lot value off the account currency.** MT5 prices a lot by `trade_tick_value`, converted at the current price. SimBroker converts a USD-based pair (USDJPY) or a cross at the entry. A limit away from the market can therefore size a step apart. USD-quoted instruments (EURUSD, GBPUSD, gold, the US indices) are exact: the parity test draws them only.
- **Paper drawdown.** Paper trades have no money account: their exposure counts open trades from the broker's truth but keeps drawdown at 0. Part 3 (running unattended) is where paper or demo gets the daily-loss kill switch.

## Testing

- `backend/tests/test_live_execution_sizing.py`: the shared rule, and SimBroker's behaviour pinned before the refactor.
- `backend/tests/test_mt5_broker_adapter.py`: the adapter on the patched `mt5` module, as today; the old fallback-to-size tests become refusals.
- `backend/tests/test_live_execution_mt5.py`: expiry, the ledger, the split, sync, the profile's symbols.
- `backend/tests/test_live_execution_account.py`: LiveAccount's anchors and persistence, against SimAccount.
- `backend/tests/test_live_execution_runner.py`: exposure before each decision, IN TRADE and attempted on MT5.
- `backend/tests/test_live_execution_parity.py`: Hypothesis, SimBroker against the MT5 adapter on a fake terminal (Requirement 8).
