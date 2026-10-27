"""
Tests for algo_backtester/config.py — run configuration, variants and the
study hold-out.

Task 197 (.kiro/specs/algo-backtester/tasks.md).
Validates: Requirements 7.1, 7.2 (.kiro/specs/algo-backtester/requirements.md)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.strategy_config import CisdMode, PendingExpiry, StopMode, StrategyConfig
from algo_backtester.config import (
    HoldoutOverlapError,
    RunConfig,
    check_holdout,
    load_or_create_study,
    load_run_config,
)
from liquidity_engine.models import Timeframe

BASE = """
[run]
profile = "exness-standard"
instruments = ["EURUSD", "XAUUSD"]
start = "2025-01-01"
end = "2026-07-01"
study = "test-study"

[account]
initial_equity = 10000.0
risk_per_trade = 0.01
compounding = false

[strategy]
entry_tf = "M15"
min_rr = 3.0
pending_expiry = "KILLZONE_END"
fallback_ttl_minutes = 180

[data]
max_gap_minutes = 30
allow_gaps = false

[report]
min_trades = 30
cost_flag_fraction = 0.25
bootstrap_resamples = 10000

[variants.min_rr_5]
strategy.min_rr = 5.0

[variants.m5_compounding]
strategy.entry_tf = "M5"
account.compounding = true
"""


def write(tmp_path: Path, text: str = BASE, name: str = "base.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_variant_dotted_key_override(tmp_path):
    base = load_run_config(write(tmp_path))
    rr5 = load_run_config(write(tmp_path), variant="min_rr_5")
    m5 = load_run_config(write(tmp_path), variant="m5_compounding")

    assert (base.variant, base.strategy.min_rr) == (None, 3.0)
    assert (rr5.variant, rr5.strategy.min_rr) == ("min_rr_5", 5.0)
    # Only the overridden keys change; everything else is the base.
    assert rr5.model_copy(update={"variant": None, "strategy": base.strategy}) == base
    assert (m5.strategy.entry_tf, m5.account.compounding, m5.strategy.min_rr) == (Timeframe.M5, True, 3.0)

    with pytest.raises(ValueError, match="min_rr_5"):  # names the variants that do exist
        load_run_config(write(tmp_path), variant="min_rr_6")


def test_stop_body_variant_in_base_config():
    # The variant task 233 measures against the default WICK stop (liquidity-engine Req 19.1).
    base_toml = Path(__file__).resolve().parents[2] / "config" / "backtests" / "base.toml"
    base = load_run_config(base_toml)
    body = load_run_config(base_toml, variant="stop_body")
    assert (base.strategy.stop_mode, body.strategy.stop_mode) == (StopMode.WICK, StopMode.BODY)
    assert body.model_copy(update={"variant": None, "strategy": base.strategy}) == base


def test_anticipation_variants_in_base_config():
    # The variants task 242 measures (liquidity-engine design, update 2026-10b).
    base_toml = Path(__file__).resolve().parents[2] / "config" / "backtests" / "base.toml"
    base = load_run_config(base_toml)

    def rules(name):
        s = load_run_config(base_toml, variant=name).strategy
        return (s.bias_mode.value, s.require_false_move, s.time_window.value, s.target_mode.value,
                s.min_stop_spreads, s.require_htf_poi, s.stop_mode.value)

    assert rules("anticipation") == ("PROFILE", True, "MANIPULATION", "NEAREST", 2.0, False, "WICK")
    assert rules("anticipation_body") == ("PROFILE", True, "MANIPULATION", "NEAREST", 2.0, False, "BODY")
    assert rules("anticipation_poi") == ("PROFILE", True, "MANIPULATION", "NEAREST", 2.0, True, "WICK")
    for name in ("anticipation", "anticipation_body", "anticipation_poi"):
        variant = load_run_config(base_toml, variant=name)
        assert variant.model_copy(update={"variant": None, "strategy": base.strategy}) == base, name


def test_fresh_raid_variants_in_base_config():
    # The variants task 344 measures (liquidity-engine Req 27, update 2026-10-21).
    base_toml = Path(__file__).resolve().parents[2] / "config" / "backtests" / "base.toml"
    base = load_run_config(base_toml)
    fresh = load_run_config(base_toml, variant="fresh").strategy
    both = load_run_config(base_toml, variant="fresh_gap").strategy
    assert base.strategy.raid_window is None
    assert (fresh.raid_window, fresh.raid_window_candles, fresh.fvg_zone.value) == (Timeframe.H4, 2, "candles")
    assert (both.raid_window, both.fvg_zone.value) == (Timeframe.H4, "gap")
    near = load_run_config(base_toml, variant="fresh_near").strategy
    full = load_run_config(base_toml, variant="fresh_near_gap").strategy
    assert (near.raid_window, near.max_stop_atr, near.target_mode.value, near.fvg_zone.value) == (
        Timeframe.H4, 1.0, "NEAREST", "candles")
    assert (full.raid_window, full.max_stop_atr, full.target_mode.value, full.fvg_zone.value) == (
        Timeframe.H4, 1.0, "NEAREST", "gap")
    assert base.strategy.max_stop_atr == 0.0
    for name in ("fresh", "fresh_gap", "fresh_near", "fresh_near_gap"):
        variant = load_run_config(base_toml, variant=name)
        assert variant.model_copy(update={"variant": None, "strategy": base.strategy}) == base, name


def test_focus_config_loads_every_variant():
    # The task 344 run: the trader's focus markets over the exploration slice, the fixes as variants.
    focus = Path(__file__).resolve().parents[2] / "config" / "backtests" / "focus.toml"
    base = load_run_config(focus)
    assert (base.run.start.isoformat(), base.run.end.isoformat()) == ("2025-01-01", "2025-07-01")
    assert "USDJPY" not in base.run.instruments and "US500" in base.run.instruments
    full = load_run_config(focus, variant="m5_fresh_near_gap").strategy
    assert (full.entry_tf, full.raid_window, full.max_stop_atr, full.target_mode.value, full.fvg_zone.value) == (
        Timeframe.M5, Timeframe.H1, 1.0, "NEAREST", "gap")
    for name in ("gap", "fresh", "fresh_near", "fresh_gap", "fresh_near_gap", "m5_gap"):
        assert load_run_config(focus, variant=name).run == base.run, name


def test_focus_config_carries_the_indicator_cisd_variants():
    # Liquidity-engine Req 30.6: the base engine and the trader's execution, each with the indicator's CISD.
    focus = Path(__file__).resolve().parents[2] / "config" / "backtests" / "focus.toml"
    base = load_run_config(focus).strategy
    execution = load_run_config(focus, variant="fresh_near_gap").strategy
    assert base.cisd is CisdMode.NEXT and execution.cisd is CisdMode.NEXT
    for mode in ("run", "crt"):
        assert load_run_config(focus, variant=mode).strategy == base.model_copy(update={"cisd": CisdMode(mode)})
        assert load_run_config(focus, variant=f"fresh_near_gap_{mode}").strategy == execution.model_copy(
            update={"cisd": CisdMode(mode)})


def test_management_is_off_by_default_and_set_by_a_variant(tmp_path):
    # Requirement 28.1: a partial and break-even, configured beside the account, not in the strategy (D43).
    text = BASE + "\n[variants.partial]\nmanagement.partial_r = 3.0\nmanagement.partial_fraction = 0.5\n"
    base = load_run_config(write(tmp_path, text))
    partial = load_run_config(write(tmp_path, text), variant="partial")
    assert base.management.partial_r == 0.0 and base.management.partial_fraction == pytest.approx(1 / 3)
    assert (partial.management.partial_r, partial.management.partial_fraction) == (3.0, 0.5)
    assert partial.strategy == base.strategy          # Phase A's cache key reads the strategy only


@pytest.mark.parametrize("fraction", [0.0, 1.0, 1.5])
def test_a_partial_leaves_a_rest(tmp_path, fraction):
    text = BASE + f"\n[management]\npartial_r = 3.0\npartial_fraction = {fraction}\n"
    with pytest.raises(ValidationError):
        load_run_config(write(tmp_path, text))


def test_focus_config_carries_the_partial_variant():
    # The rule the trader chose on 2026-10-27: a third off at 3R, the rest to break-even.
    focus = Path(__file__).resolve().parents[2] / "config" / "backtests" / "focus.toml"
    execution = load_run_config(focus, variant="fresh_near_gap")
    partial = load_run_config(focus, variant="fresh_near_gap_partial")
    assert partial.strategy == execution.strategy and execution.management.partial_r == 0.0
    assert (partial.management.partial_r, partial.management.partial_fraction) == (3.0, pytest.approx(1 / 3))


@pytest.mark.parametrize("variant", ["m5_fresh_near_gap", "fresh_near_gap", "fresh_near_gap_box"])
def test_confirmation_config_is_the_explored_version_on_the_next_period(variant):
    # The pre-registered confirmations (docs/backtests/CONFIRMATION_TRADER_EXECUTION.md, CONFIRMATION_D1_BOX.md):
    # the same version, markets, account, costs and report as focus.toml's; only the period differs, and it stops
    # before the study's hold-out.
    root = Path(__file__).resolve().parents[2] / "config" / "backtests"
    explored = load_run_config(root / "focus.toml", variant=variant)
    confirm = load_run_config(root / "confirm.toml", variant=variant)
    assert confirm.strategy == explored.strategy
    assert (confirm.account, confirm.data, confirm.report) == (explored.account, explored.data, explored.report)
    assert confirm.run.model_copy(update={"start": explored.run.start, "end": explored.run.end}) == explored.run
    assert (confirm.run.start.isoformat(), confirm.run.end.isoformat()) == ("2025-07-01", "2026-07-01")
    assert load_run_config(root / "confirm.toml").strategy == load_run_config(root / "focus.toml").strategy


@pytest.mark.parametrize("edit, key", [
    (("[account]", "[account]\nrisk_per_trde = 0.02"), "risk_per_trde"),       # typo in a section
    (("[report]", "[reports]"), "reports"),                                     # unknown section
    (("[strategy]", "[strategy]\nmin_r = 5.0"), "min_r"),                       # typo in StrategyConfig
    (("strategy.min_rr = 5.0", "strategy.min_r = 5.0"), "min_r"),              # typo in a variant
])
def test_unknown_config_key_rejected(tmp_path, edit, key):
    old, new = edit
    path = write(tmp_path, BASE.replace(old, new, 1))
    variant = "min_rr_5" if "strategy.min_r " in new else None
    with pytest.raises((ValidationError, ValueError), match=key):
        load_run_config(path, variant=variant)


@pytest.mark.parametrize("edit", [
    ('end = "2026-07-01"', 'end = "2024-07-01"'),     # end before start
    ("instruments = [\"EURUSD\", \"XAUUSD\"]", "instruments = []"),
    ("risk_per_trade = 0.01", "risk_per_trade = 0"),
])
def test_invalid_run_settings_rejected(tmp_path, edit):
    with pytest.raises(ValidationError):
        load_run_config(write(tmp_path, BASE.replace(*edit, 1)))


def test_run_config_resolves_strategy_config(tmp_path):
    cfg = load_run_config(write(tmp_path))
    assert isinstance(cfg.strategy, StrategyConfig)
    assert cfg.strategy == StrategyConfig(entry_tf="M15", min_rr=3.0, pending_expiry=PendingExpiry.KILLZONE_END,
                                          fallback_ttl_minutes=180)
    assert (cfg.run.start, cfg.run.end) == (date(2025, 1, 1), date(2026, 7, 1))
    assert cfg.run.instruments == ("EURUSD", "XAUUSD")


def test_config_without_optional_tables_uses_defaults(tmp_path):
    # Only [run] is required; the live StrategyConfig defaults apply (found by the task 218 sample run).
    path = tmp_path / "minimal.toml"
    path.write_text('[run]\nprofile = "exness-standard"\ninstruments = ["EURUSD"]\nstart = 2026-09-30\n'
                    'end = 2026-10-02\nstudy = "s"\n', encoding="utf-8")
    cfg = load_run_config(path)
    assert cfg.strategy == StrategyConfig() and cfg.account.risk_per_trade == 0.01
    assert cfg.report.chart_bars_before == 60


def test_study_holdout_defaults_to_last_3_months_and_persists(tmp_path):
    study = load_or_create_study("test-study", data_end=date(2026, 7, 1), root=tmp_path)
    assert study.holdout_start == date(2026, 4, 1)  # D7: the most recent 3 months of data
    path = tmp_path / "config" / "backtests" / "studies" / "test-study.toml"
    assert path.exists()

    # Set once per study: more data later doesn't move it.
    again = load_or_create_study("test-study", data_end=date(2026, 12, 1), root=tmp_path)
    assert again.holdout_start == date(2026, 4, 1)

    # Month-end arithmetic clamps to the shorter month.
    assert load_or_create_study("other", data_end=date(2026, 5, 31), root=tmp_path).holdout_start == date(2026, 2, 28)


def test_run_overlapping_holdout_refused_unless_final(tmp_path):
    study = load_or_create_study("test-study", data_end=date(2026, 7, 1), root=tmp_path)
    cfg = load_run_config(write(tmp_path))  # 2025-01-01 .. 2026-07-01 overlaps 2026-04-01 onward

    with pytest.raises(HoldoutOverlapError, match="2026-04-01"):
        check_holdout(cfg, study, final=False)
    check_holdout(cfg, study, final=True)  # the final validation run may include it

    in_sample = cfg.model_copy(update={"run": cfg.run.model_copy(update={"end": date(2026, 4, 1)})})
    check_holdout(in_sample, study, final=False)  # [start, end) stops at the hold-out: fine


def test_committed_base_config_loads():
    root = Path(__file__).resolve().parents[2]
    cfg = load_run_config(root / "config" / "backtests" / "base.toml")
    assert isinstance(cfg, RunConfig) and cfg.run.profile == "exness-standard"
    assert load_run_config(root / "config" / "backtests" / "base.toml", variant="min_rr_5").strategy.min_rr == 5.0
