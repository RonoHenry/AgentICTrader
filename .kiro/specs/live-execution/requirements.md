# Requirements Document

**spec**: Live Execution: safe orders on the broker (part 1 of "the backend is done")

## Introduction

The backtester's results transfer to a broker only if live orders are sized, expired, counted, limited and managed the way the backtest does them. The audit of 2026-10-10 found that the MT5 path (`scripts/run_live_agent.py --broker mt5`, `agent/brokers/mt5.py`) differs. A recheck on 2026-11-25 found every gap still open, plus two more:

1. **Lot sizing.** It rounds to the nearest step and clamps up to `volume_min`. It has no floor on the stop distance, so a stop a hair from the entry sizes to `volume_max`; a backtest intent once sized 200 lots. When the lots can't be computed it falls back to `order["size"]`, which is in OANDA units.
2. **Expiry.** Limits are GTC. Nothing cancels them at the end of the killzone.
3. **The trade count.** It is freed only on paper, so live MT5 blocks every setup after 3 trades until a restart.
4. **Drawdown.** Daily and weekly drawdown are seeded at 0 and never updated. Equity is a fixed $200, so the 3% and 6% stops can't fire.
5. **Management.** The partial and break-even (algo-backtester Req 28) never run on MT5.
6. **One trade per market.** On MT5, nothing stops a second order on a market that already has one.
7. **Symbols.** With `--config`, candles are read through the broker profile's symbols (`EURUSDm`), but orders go to the instrument plus `MT5_SYMBOL_SUFFIX`.

This spec closes those gaps. It is part 1 of four (2026-11-25): part 2 connects the Thesis Engine to the broker, part 3 runs unattended, part 4 is the memory. Nothing here trades real money: the target is the Exness demo.

## Glossary

- **Budget:** the money one trade risks, `risk_per_trade` times the account (Requirement 4.2).
- **Ledger:** the runner's record of the trades it placed on MT5, persisted to a file. The terminal is the truth for each ticket's state; the ledger groups tickets into trades.
- **Trade:** one order intent. Unmanaged it is one ticket; with the partial (Requirement 7) it is two.
- **Own:** placed by this runner, tagged with its magic number.

## Requirements

### Requirement 1: Sizing as the backtest sizes

**User Story:** As the trader, I want a live order sized exactly as the backtest sized it, so a demo result means what the backtest meant.

#### Acceptance Criteria

1. WHEN an order carries `risk_amount` THE MT5 adapter SHALL size it as SimBroker does: `risk_amount / (|reference - stop| x money per lot per price unit)`, rounded DOWN to `volume_step` and capped at `volume_max`. The reference is the limit price, or the market price for a market order. Money per price unit is the symbol's `trade_tick_value / trade_tick_size`.
2. WHEN that is under `volume_min`, THE adapter SHALL send `volume_min` only if its risk is within the budget plus 10%. Otherwise it SHALL refuse with `MIN_VOLUME_OVER_RISK`.
3. THE rule SHALL be one function, shared by SimBroker and the MT5 adapter. SimBroker's results SHALL NOT change.
4. WHEN an order carries `risk_amount` but no stop, or the symbol has no tick value, THE adapter SHALL refuse it (`INVALID_ORDER`, `NO_TICK_VALUE`). It SHALL NOT fall back to `order["size"]`.
5. AN order without `risk_amount` (a manual order) SHALL keep its explicit size, rounded to the step.

### Requirement 2: The stop backstop

**User Story:** As the trader, I want an order refused when the spread and slippage alone could make a stop-out cost far more than the budget, so a bad stop can't blow up the account.

#### Acceptance Criteria

1. WHEN the live spread plus the instrument's stop slippage is more than `max_stop_overrun` times `|reference - stop|`, THE MT5 adapter SHALL refuse the order with `STOP_TOO_TIGHT`. The default is 0.5: costs alone can't take a stop-out past 1.5 times the budget.
2. SimBroker SHALL accept the same setting, off by default, so recorded results don't change (LX-D1).
3. A refusal SHALL reach the decision log as a SKIP carrying its code.

### Requirement 3: Pending orders expire as in the backtest

**User Story:** As the trader, I want an unfilled limit cancelled when the backtest would cancel it, so live orders don't rest into sessions the backtest never traded.

#### Acceptance Criteria

1. A pending order's expiry SHALL be `pending_expiry(placed_at, cfg.pending_expiry, cfg.fallback_ttl)`, the function the paper and sim brokers use.
2. WHEN the symbol's `expiration_mode` allows SPECIFIED, THE order SHALL be sent `ORDER_TIME_SPECIFIED` with its expiry in server time. Otherwise it SHALL be sent GTC.
3. EVERY minute, THE runner SHALL cancel each own pending order past its expiry, however it was sent.
4. AN order whose expiry is not after its placement (placed at the end of a killzone) SHALL NOT be sent. It SHALL be recorded as expired, as the backtest records it.

### Requirement 4: The account the risk engine sees

**User Story:** As the trader, I want the drawdown limits and the trade limit to work live, so the account stops itself the way the backtest's does.

#### Acceptance Criteria

1. BEFORE every decision, THE runner SHALL write the exposure from the broker's truth:
   - open trades: own trades pending or open at the broker;
   - balance and equity: from the terminal;
   - daily and weekly drawdown: from anchors set at the start of each strategy-calendar D1 and W1 period, exactly as SimAccount sets them.
2. THE budget SHALL be `risk_per_trade` times the balance at the run's first start (`compounding = false`), or times the current balance (`compounding = true`), from the run configuration's `[account]`. The fixed `_DEMO_EQUITY` SHALL NOT be used on MT5.
3. THE initial balance and the anchors SHALL survive a restart.
4. WHEN the daily drawdown reaches 3%, or the weekly 6%, THE risk engine SHALL refuse new orders, as it does in the backtest.

### Requirement 5: One trade per market, one attempt per setup

#### Acceptance Criteria

1. ON MT5, a market with an own trade pending or open SHALL NOT be evaluated (IN TRADE), as on paper and in the backtest.
2. A setup_id that was ordered before SHALL NOT be ordered again (algo-backtester D6), on MT5 and on paper, across restarts.

### Requirement 6: The run's broker profile

#### Acceptance Criteria

1. WITH `--config`, orders SHALL use the profile's symbols, so fetching and ordering use the same symbol.
2. WITH `--config`, the runner SHALL use the profile's server clock, for reading bars and for the expiry it sends.

### Requirement 7: The partial and break-even on MT5

**User Story:** As the trader, I want the live trade managed as the backtest managed it, a third at 3R and the rest to break-even.

#### Acceptance Criteria

1. WITH `[management] partial_r` set, THE order SHALL be split into two tickets at placement, using SimBroker's rule:
   - the part is the lots times `partial_fraction`, rounded down;
   - the trade runs unmanaged when the part or the rest would be under `volume_min` (algo-backtester D44), or when the partial level is at or beyond the target;
   - the part's target is the partial level; the rest's target is the trade's target.
2. ONCE a ticket fills, its partial level SHALL be recomputed from the actual fill, as the backtest computes it from its fill.
3. WHEN the part has closed and the rest is still open, THE runner SHALL move the rest's stop to its fill within a minute.
4. A split trade SHALL count once toward open trades and once toward one trade per market.

### Requirement 8: The parity test

#### Acceptance Criteria

1. A property-based test SHALL give SimBroker and the MT5 adapter (on a fake terminal built from the same instrument spec) the same account, order and market. It SHALL check that both agree on:
   - refused or not, and the reason;
   - limit or market;
   - the lots;
   - the expiry instant;
   - the split.

### Requirement 9: The demo check

#### Acceptance Criteria

1. **(User action: the MT5 terminal logged into the Exness demo.)** THE runner SHALL run one session on the demo with `--broker mt5 --config`. The ledger and the terminal SHALL agree on every order, expiry, partial and stop move.
