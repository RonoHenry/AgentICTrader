# Implementation Plan

**spec**: Live Execution: safe orders on the broker

## Overview

- **Numbering:** tasks continue the platform sequence from **453**.
- **Order:** sizing first (the real-money danger), then the profile, expiry, the account, one trade per market, management, and the parity test. The demo check is the trader's.
- **TDD:** every code task is RED → GREEN → REFACTOR. The tests are in `backend/tests/test_live_execution_*.py` and `test_mt5_broker_adapter.py`.
- **Recorded results stay:** SimBroker's behaviour is pinned before it is refactored. Nothing in `ENGINE_SOURCES` changes.
- **Demo only:** nothing here is run against a real-money account.
- **One commit per task**, pushed to the open PR.

## Tasks

- [x] 453. The spec (Requirements 1-9)
  - The requirements, the design with decisions LX-D1 to D7, and this plan, after the 2026-11-25 recheck of the 2026-10-10 audit.
  - **Validates: the scope**

- [x] 454. Sizing as the backtest sizes, and the stop backstop (Requirements 1, 2)
  - `agent/brokers/sizing.py`: `round_down`, `lots_for_risk` (`MIN_VOLUME_OVER_RISK`), `split_lots` (D44), `stop_overrun`, `SizingError`.
  - SimBroker calls them, pinned by tests written before the change; `max_stop_overrun` is optional and off.
  - MT5 adapter: risk-sized orders round down, refuse min-over-risk, `STOP_TOO_TIGHT` (default 0.5), and refuse instead of falling back to `size` (`INVALID_ORDER`, `NO_TICK_VALUE`). Manual orders keep their size.
  - **Done 2026-11-27.**
    - Tests: `test_live_execution_sizing.py` (18, one Hypothesis) and `test_mt5_broker_adapter.py` (the two fallback-to-size tests replaced by 10 refusal tests).
    - SimBroker's own tests, the golden journals and the run modes pass unchanged.
    - `MT5BrokerError` carries a `reason`.
  - **Validates: Requirements 1.1-1.5, 2.1-2.3**

- [x] 455. The run's broker profile on MT5 (Requirement 6)
  - The adapter takes a symbol map; the runner passes the profile's, and uses the profile's server clock with `--config`.
  - **Done 2026-11-27.**
    - `MT5BrokerAdapter(symbol_of=...)`.
    - `run_live_agent._mt5_broker_client(run_cfg)` passes the profile's symbols and specs.
    - `_server_clock(run_cfg)` replaces the environment's clock with the profile's.
    - Tests: `test_live_execution_runner.py` (5), `test_live_execution_mt5.py` (1).
  - **Validates: Requirements 6.1, 6.2**

- [ ] 456. Expiry, and the ledger (Requirement 3)
  - `MT5Ledger`: own trades persisted, write-then-rename.
  - The order is sent `ORDER_TIME_SPECIFIED` with server-time expiration when the symbol allows it, otherwise GTC. One expiring at placement isn't sent (LX-D7).
  - `sync(now)` cancels own pending orders past their expiry and closes out finished trades.
  - **Validates: Requirements 3.1-3.4**

- [ ] 457. The account from the terminal (Requirement 4)
  - `LiveAccount(SimAccount)`: `sync(t, balance, equity, open_trades)`, with the initial balance and anchors persisted.
  - The runner on MT5: the per-minute sync, and the exposure written before every decision. `_DEMO_EQUITY` is gone from MT5.
  - **Validates: Requirements 4.1-4.4**

- [ ] 458. One trade per market, one attempt per setup (Requirement 5)
  - MT5: IN TRADE from the ledger after sync; attempted setups from the ledger.
  - Paper: attempted setups from its trade file; open trades from its trades before each decision.
  - **Validates: Requirements 5.1, 5.2**

- [ ] 459. The partial and break-even on MT5 (Requirement 7)
  - Placement splits with `split_lots` and `partial_level`. `sync` recomputes the part's target from its fill and moves the rest to break-even once the part has closed.
  - **Validates: Requirements 7.1-7.4**

- [ ] 460. The parity test (Requirement 8)
  - Hypothesis over instruments, budgets, stops, markets and times: SimBroker and the adapter on a fake terminal agree.
  - **Validates: Requirement 8.1**

- [ ] 461. The demo check **(user action: the MT5 terminal on the Exness demo)**
  - One session with `--broker mt5 --config config/backtests/focus.toml --variant <the trader's>`. The ledger is compared with the terminal's history.
  - **Validates: Requirement 9.1**
