"""
Tests for algo_research/config.py — ResearchConfig, the slices and the hold-out.

Task 244 (.kiro/specs/algo-research/tasks.md).
Validates: Requirements 13.1, 13.2 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agent.strategy_config import StrategyConfig
from algo_research.config import (
    HoldoutError,
    ResearchConfig,
    load_research_config,
    trading_date,
    trading_date_open,
)

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
MIN = timedelta(minutes=1)

RESEARCH = """
profile = "exness-standard"
study = "test-study"
instruments = ["EURUSD", "XAUUSD"]
start = 2025-01-01
snapshot = "test-snapshot"

[slices]
explore = [2025-01-01, 2025-07-01]
confirm = [2025-07-01, 2026-07-07]
"""


def write_root(tmp_path: Path, research: str = RESEARCH, holdout: str = "2026-07-07") -> Path:
    (tmp_path / "config" / "research").mkdir(parents=True)
    (tmp_path / "config" / "research" / "research.toml").write_text(research, encoding="utf-8")
    studies = tmp_path / "config" / "backtests" / "studies"
    studies.mkdir(parents=True)
    (studies / "test-study.toml").write_text(
        f"holdout_start = {holdout}\ncreated_from_data_end = 2026-10-07\n", encoding="utf-8")
    return tmp_path


def test_loads_research_toml_defaults():
    cfg = load_research_config()                       # the committed config/research/research.toml
    assert cfg.profile == "exness-standard"
    assert cfg.study == "baseline-2026q3"
    assert cfg.instruments == ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
    assert cfg.start == date(2025, 1, 1)
    assert cfg.holdout_start == date(2026, 7, 7)       # read from the study, never set here
    assert cfg.slices.explore == (date(2025, 1, 1), date(2025, 7, 1))
    assert cfg.slices.confirm == (date(2025, 7, 1), date(2026, 7, 7))
    assert cfg.bootstrap.resamples == 10_000
    assert cfg.baselines.random_time_draws == 20
    assert cfg.baselines.shuffles == 200
    # The engine sees what Phase A sees: the backtester's base [strategy].
    assert isinstance(cfg.strategy(), StrategyConfig)
    assert cfg.strategy().entry_tf.value == "M15"


def test_loads_from_any_root(tmp_path):
    cfg = load_research_config(root=write_root(tmp_path))
    assert cfg.instruments == ("EURUSD", "XAUUSD")
    assert cfg.snapshot == "test-snapshot"


@pytest.mark.parametrize("slices, slice_name", [
    ("explore = [2025-01-01, 2025-06-01]\nconfirm = [2025-07-01, 2026-07-07]", "confirm"),   # a gap
    ("explore = [2025-01-01, 2025-08-01]\nconfirm = [2025-07-01, 2026-07-07]", "confirm"),   # an overlap
    ("explore = [2025-02-01, 2025-07-01]\nconfirm = [2025-07-01, 2026-07-07]", "explore"),   # not at start
    ("explore = [2025-01-01, 2025-07-01]\nconfirm = [2025-07-01, 2026-06-01]", "confirm"),   # ends early
    ("explore = [2025-07-01, 2025-01-01]\nconfirm = [2025-07-01, 2026-07-07]", "explore"),   # backwards
])
def test_slices_must_be_contiguous_and_end_at_holdout(tmp_path, slices, slice_name):
    research = RESEARCH.split("[slices]")[0] + "[slices]\n" + slices + "\n"
    with pytest.raises(ValueError, match=slice_name):
        load_research_config(root=write_root(tmp_path, research))


def test_period_reaching_holdout_refused(tmp_path):
    # Property 10: a confirmation slice running past the hold-out start is refused, naming it.
    research = RESEARCH.replace("confirm = [2025-07-01, 2026-07-07]", "confirm = [2025-07-01, 2026-08-01]")
    with pytest.raises(HoldoutError, match="holdout_start 2026-07-07"):
        load_research_config(root=write_root(tmp_path, research))

    cfg = load_research_config(root=write_root(tmp_path / "ok"))
    with pytest.raises(HoldoutError, match="2026-07-07"):
        cfg.check_end(date(2026, 7, 8))
    cfg.check_end(date(2026, 7, 7))                     # ending at the hold-out start is fine


def test_unknown_key_refused(tmp_path):
    with pytest.raises(ValueError, match="instrumentz"):
        load_research_config(root=write_root(tmp_path, RESEARCH.replace("instruments", "instrumentz")))


def test_missing_study_refused(tmp_path):
    root = write_root(tmp_path)
    (root / "config" / "backtests" / "studies" / "test-study.toml").unlink()
    with pytest.raises(FileNotFoundError, match="test-study"):
        load_research_config(root=root)


def test_trading_date_17_00_boundary():
    assert trading_date(datetime(2026, 1, 11, 17, 0, tzinfo=NY)) == date(2026, 1, 12)    # Sunday 17:00 is Monday
    assert trading_date(datetime(2026, 1, 16, 16, 59, tzinfo=NY)) == date(2026, 1, 16)   # Friday 16:59 is Friday
    assert trading_date_open(date(2026, 1, 12)) == datetime(2026, 1, 11, 17, 0, tzinfo=NY).astimezone(UTC)
    assert trading_date_open(date(2026, 7, 7)) == datetime(2026, 7, 6, 21, 0, tzinfo=UTC)   # EDT: 17:00 is 21:00 UTC


def test_slice_of_boundaries(tmp_path):
    cfg: ResearchConfig = load_research_config(root=write_root(tmp_path))
    explore_start = trading_date_open(date(2025, 1, 1))
    confirm_start = trading_date_open(date(2025, 7, 1))
    holdout = trading_date_open(date(2026, 7, 7))

    assert cfg.slice_of(explore_start - MIN) is None
    assert cfg.slice_of(explore_start) == "explore"                 # starts are inclusive
    assert cfg.slice_of(confirm_start - MIN) == "explore"           # ends are exclusive
    assert cfg.slice_of(confirm_start) == "confirm"
    assert cfg.slice_of(holdout - MIN) == "confirm"
    assert cfg.slice_of(holdout) is None                             # the hold-out's first trading date
    assert cfg.slice_of(datetime(2026, 7, 7, 0, 0, tzinfo=UTC)) is None

    # The research period runs from the first explore trading date to the hold-out's first.
    assert cfg.period == (explore_start, holdout)
    assert cfg.slice_period("confirm") == (confirm_start, holdout)
    with pytest.raises(ValueError, match="slice"):
        cfg.slice_period("holdout")
