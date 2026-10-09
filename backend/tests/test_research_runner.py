"""
Tests for the runner, ledger, reports and CLI (algo_research/runner.py,
ledger.py, report.py, cli.py): explore, run, and pre-registration.

Task 254 (.kiro/specs/algo-research/tasks.md). A temporary git repository in
tmp_path holds the configuration, the hypotheses and a stand-in algo_research/;
the data is the backtester's fixture week, snapshotted and built once.
Validates: Requirements 8.2-8.4, 12.1-12.4, 13.1 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

import csv
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from algo_research.cli import main
from algo_research.ledger import LEDGER_COLUMNS, read_ledger, render_ledger_md
from tests.test_research_snapshot import MultiFixtureSource, fixture_root

UTC = timezone.utc
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)

DIRECTION = '''
id = "H901"
title = "Fixture: the side of the midnight open calls the rest of the day"
statement = "At 05:00 and 09:00 New York, the rest of the day moves away from the midnight open."
family = "fixture"
created = 2026-10-10

[event]
name = "anchor"
params = { at = "05:00", direction_from = "side_midnight_open" }

[vary]
key = "event.params.at"
values = ["05:00", "09:00"]

[measure]
kind = "direction"

[baselines]
use = ["naive:always_long", "naive:prev_day_dir", "random_time"]

[pass]
min_events = 1
min_days = 1
require = [{ stat = "accuracy", versus = "best_naive" }, { stat = "accuracy", versus = "random_time" }]
'''

RACE = '''
id = "H902"
title = "Fixture: a 1R race from the 09:00 close, in the direction of the H4 candle just closed"
statement = "From 09:00 New York, a race toward 1 ATR away with a 0.5 ATR stop."
family = "fixture"
created = 2026-10-10

[event]
name = "anchor"
params = { at = "09:00", direction_from = "prev_h4_dir" }

[measure]
kind = "race"

[trade]
stop = { kind = "atr", value = 0.25 }
target = { kind = "r", value = 1.0 }
time_limit = { minutes = 240 }

[baselines]
use = ["coin_flip", "random_time"]

[pass]
min_events = 1
min_days = 1
require = [{ stat = "win_rate", versus = "coin_flip" }, { stat = "mean_net_r" }]
'''

DAILY = '''
id = "H903"
title = "Fixture: lows of up days in the 01/05/09 H4 candles"
statement = "On up days the low forms in the 01:00, 05:00 or 09:00 H4 candle more often than shuffled paths."
family = "replication"
created = 2026-10-10

[event]
name = "daily"

[measure]
kind = "rate"
of = "day_low_h4 in [2, 3, 4]"
given = "day_dir == 1"

[baselines]
use = ["shuffled_path"]

[pass]
min_events = 1
min_days = 1
require = [{ stat = "rate", versus = "shuffled_path" }]
'''


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture(scope="module")
def data_dirs(tmp_path_factory) -> dict:
    """The fixture week snapshotted and built once: explore Sep 29-30, confirm Sep 30-Oct 2."""
    base = tmp_path_factory.mktemp("research-data")
    root = _config(base / "config-root")
    dirs = dict(snapshots_dir=base / "snapshots", cache_dir=base / "cache")
    assert main(["snapshot"], source_factory=lambda profile: MultiFixtureSource(), root=root, **dirs) == 0
    assert main(["build", "--workers", "1"], root=root, **dirs) == 0
    return dirs


def _config(root: Path) -> Path:
    fixture_root(root, profile="exness-standard")
    research = root / "config" / "research" / "research.toml"
    research.write_text(research.read_text(encoding="utf-8")
                        .replace("explore = [2026-09-29, 2026-10-01]", "explore = [2026-09-29, 2026-09-30]")
                        .replace("confirm = [2026-10-01, 2026-10-02]", "confirm = [2026-09-30, 2026-10-02]")
                        + "\n[bootstrap]\nresamples = 500\n\n[baselines]\nrandom_time_draws = 3\nshuffles = 20\n",
                        encoding="utf-8")
    return root


@pytest.fixture
def repo(tmp_path, data_dirs) -> Path:
    root = _config(tmp_path / "repo")
    hypotheses = root / "config" / "research" / "hypotheses"
    hypotheses.mkdir(parents=True)
    for name, text in (("H901-fixture-direction.toml", DIRECTION), ("H902-fixture-race.toml", RACE),
                       ("H903-fixture-daily.toml", DAILY)):
        (hypotheses / name).write_text(text, encoding="utf-8")
    (root / "algo_research").mkdir()
    (root / "algo_research" / "marker.py").write_text("# stand-in for the package\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    return root


def cli(repo: Path, data_dirs: dict, *argv: str, capsys=None) -> tuple[int, str]:
    code = main(list(argv), root=repo, drafts_dir=repo / "drafts", now=lambda: NOW, **data_dirs)
    return code, capsys.readouterr().out if capsys else ""


def ledger(repo: Path) -> list[dict]:
    return read_ledger(repo / "docs" / "research" / "ledger.csv")


# ── Property 11: pre-registration is enforced ───────────────────────────────

def test_run_refuses_an_uncommitted_hypothesis(repo, data_dirs, capsys):
    (repo / "config" / "research" / "hypotheses" / "H904-new.toml").write_text(
        DIRECTION.replace('"H901"', '"H904"'), encoding="utf-8")
    code, out = cli(repo, data_dirs, "run", "H904", capsys=capsys)
    assert code == 2 and "not committed" in out
    assert not ledger(repo)


def test_run_refuses_a_modified_hypothesis(repo, data_dirs, capsys):
    path = repo / "config" / "research" / "hypotheses" / "H901-fixture-direction.toml"
    path.write_text(DIRECTION.replace("min_days = 1", "min_days = 2"), encoding="utf-8")
    code, out = cli(repo, data_dirs, "run", "H901", capsys=capsys)
    assert code == 2 and "uncommitted changes" in out and "supersedes" in out


def test_run_refuses_uncommitted_code(repo, data_dirs, capsys):
    (repo / "algo_research" / "marker.py").write_text("# edited\n", encoding="utf-8")
    code, out = cli(repo, data_dirs, "run", "H901", capsys=capsys)
    assert code == 2 and "algo_research/ has uncommitted changes" in out


def test_run_refuses_an_id_in_the_ledger_with_another_hash(repo, data_dirs, capsys):
    assert cli(repo, data_dirs, "run", "H903", capsys=capsys)[0] == 0
    path = repo / "config" / "research" / "hypotheses" / "H903-fixture-daily.toml"
    path.write_text(DAILY.replace("min_days = 1", "min_days = 2"), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "edit H903")
    code, out = cli(repo, data_dirs, "run", "H903", capsys=capsys)
    assert code == 2 and "already in the ledger with another hash" in out and 'supersedes = "H903"' in out
    assert len(ledger(repo)) == 1


def test_explore_never_writes_the_ledger(repo, data_dirs, capsys):
    code, out = cli(repo, data_dirs, "explore", "H901", capsys=capsys)
    assert code == 0 and "not in the ledger" in out
    assert not (repo / "docs" / "research" / "ledger.csv").exists()
    [draft] = (repo / "drafts").glob("H901-*.md")
    assert draft.name == "H901-20261010-090000.md"
    assert "explore slice" in draft.read_text(encoding="utf-8")
    # explore needs no commit: an edited hypothesis explores fine.
    path = repo / "config" / "research" / "hypotheses" / "H901-fixture-direction.toml"
    path.write_text(DIRECTION.replace("min_days = 1", "min_days = 2"), encoding="utf-8")
    assert cli(repo, data_dirs, "explore", "H901", capsys=capsys)[0] == 0


# ── the ledger ──────────────────────────────────────────────────────────────

def test_run_appends_one_row_per_test_and_never_rewrites(repo, data_dirs, capsys):
    assert cli(repo, data_dirs, "run", "H901", capsys=capsys)[0] == 0
    rows = ledger(repo)
    assert [(r["seq"], r["hypothesis"], r["test"]) for r in rows] == [("1", "H901", "at=05:00"),
                                                                      ("2", "H901", "at=09:00")]
    assert all(r["slice"] == "confirm" and r["run_at"] == "2026-10-10T09:00:00+00:00" for r in rows)
    assert rows[0]["rule_1"] == "accuracy vs best_naive" and rows[0]["rule_2"] == "accuracy vs random_time"
    assert rows[0]["code_commit"] == git(repo, "rev-parse", "HEAD").strip()
    before = (repo / "docs" / "research" / "ledger.csv").read_bytes()

    assert cli(repo, data_dirs, "run", "H902", capsys=capsys)[0] == 0
    after = (repo / "docs" / "research" / "ledger.csv").read_bytes()
    assert after.startswith(before)                                # earlier rows byte-identical
    assert [r["seq"] for r in ledger(repo)] == ["1", "2", "3"]
    with (repo / "docs" / "research" / "ledger.csv").open(encoding="utf-8", newline="") as fh:
        assert tuple(next(csv.reader(fh))) == LEDGER_COLUMNS


def test_rerun_same_hash_reproduces_and_a_mismatch_names_the_fields(repo, data_dirs, capsys):
    assert cli(repo, data_dirs, "run", "H902", capsys=capsys)[0] == 0
    first = (repo / "docs" / "research" / "ledger.csv").read_bytes()
    code, out = cli(repo, data_dirs, "run", "H902", capsys=capsys)
    assert code == 0 and "reproduced ledger row 1 exactly" in out
    assert (repo / "docs" / "research" / "ledger.csv").read_bytes() == first      # nothing appended

    path = repo / "docs" / "research" / "ledger.csv"
    text = path.read_text(encoding="utf-8")
    row = ledger(repo)[0]
    path.write_text(text.replace(f",{row['n_events']},{row['n_dates']},",
                                 f",{int(row['n_events']) + 1},{row['n_dates']},"), encoding="utf-8")
    code, out = cli(repo, data_dirs, "run", "H902", capsys=capsys)
    assert code == 1 and "differs from ledger row 1" in out and "n_events" in out


def test_run_reads_only_the_confirmation_slice_and_explore_only_exploration(repo, data_dirs):
    from agent.broker_profiles import load_profile
    from algo_research.config import load_research_config
    from algo_research.dataset import build_dataset
    from algo_research.features.cache import ParquetCache
    from algo_research.hypothesis import load_hypothesis
    from algo_research.races import RaceCosts
    from algo_research.runner import RunSettings, run_test
    from algo_research.snapshot import load_snapshot

    cfg = load_research_config(root=repo)
    snapshot = load_snapshot(data_dirs["snapshots_dir"] / cfg.snapshot)
    specs = load_profile(cfg.profile).specs()
    data = build_dataset(snapshot, cfg, specs, cfg.strategy(repo), ParquetCache(data_dirs["cache_dir"]), workers=1)
    h = load_hypothesis(repo / "config" / "research" / "hypotheses" / "H902-fixture-race.toml")
    costs = {i: RaceCosts.from_spec(specs[i], "USD") for i in data.frames}
    settings = RunSettings(resamples=200, random_time_draws=2)
    for slice_name, dates in (("confirm", {date(2026, 9, 30), date(2026, 10, 1)}),
                              ("explore", {date(2026, 9, 29)})):
        [test] = h.tests()
        result = run_test(test, data, slice_name, costs, seed=1, settings=settings)
        assert len(result.events) > 0
        assert {d.date() for d in pd.DatetimeIndex(result.events["trading_date"])} <= dates

    # Random times come from the same slice, on dates without an event: Wednesday's events draw Thursday.
    from algo_research.hypothesis import parse_hypothesis
    [test] = parse_hypothesis(RACE.replace('params = { at = "09:00", direction_from = "prev_h4_dir" }',
                                           'params = { at = "09:00", direction_from = "prev_h4_dir" }\n'
                                           'where = "weekday == 2"')).tests()
    result = run_test(test, data, "confirm", costs, seed=1, settings=settings)
    assert {d.date() for d in pd.DatetimeIndex(result.events["trading_date"])} == {date(2026, 9, 30)}
    drawn = result.extra["draw_races"]
    assert len(drawn) > 0
    rows = data.features[data.features["t"].isin(drawn["t"])]
    assert set(rows["slice"]) == {"confirm"} and set(rows["trading_date"].dt.date) == {date(2026, 10, 1)}


# ── reports ─────────────────────────────────────────────────────────────────

def test_report_has_every_section(repo, data_dirs, capsys):
    assert cli(repo, data_dirs, "run", "H902", capsys=capsys)[0] == 0
    text = (repo / "docs" / "research" / "reports" / "H902.md").read_text(encoding="utf-8")
    for heading in ("# H902: ", "## The question as registered", "### Sample", "### Results", "### Stability",
                    "### Races", "### Check by eye", "## Inputs"):
        assert heading in text, heading
    assert "sha256 `" in text and 'id = "H902"' in text                 # the file as registered
    assert "**EURUSD**" in text and "**XAUUSD**" in text                # event times per instrument
    assert "Ambiguous bars" in text and "MFE (R) quartiles" in text
    assert "ledger row 1" in text and "typical spread" in text
    assert "By instrument:" in text and "By weekday:" in text and "By year:" in text


def test_report_lists_at_most_20_events_per_instrument():
    from algo_research.report import _by_eye

    events = pd.DataFrame({"row": range(30), "t": pd.date_range("2026-01-05 14:00", periods=30, freq="1D", tz="UTC"),
                           "instrument": "EURUSD", "trading_date": pd.date_range("2026-01-05", periods=30),
                           "direction": "LONG", "level": 1.1})

    class R:
        pass

    r = R()
    r.events = events
    table_rows = [line for line in _by_eye(r) if line.startswith("| 2026-")]
    assert len(table_rows) == 20


def test_ledger_md_counts_per_family_and_expected_passes(repo, data_dirs, capsys):
    assert cli(repo, data_dirs, "run", "H901", capsys=capsys)[0] == 0
    assert cli(repo, data_dirs, "run", "H903", capsys=capsys)[0] == 0
    assert cli(repo, data_dirs, "ledger", capsys=capsys)[0] == 0
    text = (repo / "docs" / "research" / "LEDGER.md").read_text(encoding="utf-8")
    assert "Official tests: **3**" in text
    assert "## fixture" in text and "## replication" in text
    assert "2 test(s);" in text and "1 test(s);" in text
    assert "Expected by chance if nothing is there: at most **0.075**" in text
    assert "[H901.md](reports/H901.md)" in text
    assert render_ledger_md([]).count("No official test") == 1


def test_random_time_draws_without_atr_are_skipped_not_raced(repo, data_dirs):
    # A drawn row with no atr_d1 can't take the event's distances: it is counted, never raced with a NaN stop.
    from agent.broker_profiles import load_profile
    from algo_research.config import load_research_config
    from algo_research.dataset import build_dataset
    from algo_research.features.cache import ParquetCache
    from algo_research.hypothesis import parse_hypothesis
    from algo_research.runner import RunSettings, run_test
    from algo_research.snapshot import load_snapshot

    cfg = load_research_config(root=repo)
    snapshot = load_snapshot(data_dirs["snapshots_dir"] / cfg.snapshot)
    data = build_dataset(snapshot, cfg, load_profile(cfg.profile).specs(), cfg.strategy(repo),
                         ParquetCache(data_dirs["cache_dir"]), workers=1)
    thursday = data.features["trading_date"].dt.date == date(2026, 10, 1)
    data.features.loc[thursday, "atr_d1"] = float("nan")
    [test] = parse_hypothesis(RACE.replace('params = { at = "09:00", direction_from = "prev_h4_dir" }',
                                           'params = { at = "09:00", direction_from = "prev_h4_dir" }\n'
                                           'where = "weekday == 2"')).tests()
    result = run_test(test, data, "confirm", {}, seed=1, settings=RunSettings(resamples=200, random_time_draws=2))
    assert len(result.events) == 2 and list(result.draws_available) == [1, 1]     # Thursday is the only other date
    assert result.skipped["draw_null_level"] == 2
    assert result.extra["draw_races"]["outcome"].isna().all()                  # none was raced
    assert result.table["n:random_time:win_rate"].sum() == 0


def test_crt_race_ends_at_c3s_close_and_draws_keep_its_duration():
    # Update 2026-10c: time_limit = "event", and `where` over the event's direction (Req 9.5, 15.3).
    from algo_research.hypothesis import parse_hypothesis
    from algo_research.runner import RunSettings, run_test
    from tests.research_fixtures import crt_path, ny, research_data
    from tests.test_research_hypothesis import CRT

    frame = crt_path(start=ny(2025, 12, 7, 17), end=ny(2026, 1, 9, 17)).frame()   # four weeks: atr_d1 is known
    data = research_data({"EURUSD": frame}, {"explore": (date(2026, 1, 5), date(2026, 1, 10))})
    [test] = parse_hypothesis(CRT.replace('where = ""', '''where = "direction == 'LONG'"''')).tests()
    result = run_test(test, data, "explore", {}, seed=1, settings=RunSettings(resamples=200, random_time_draws=3))
    assert [t.to_pydatetime() for t in result.events["t"]] == [ny(2026, 1, 5, 4, 0), ny(2026, 1, 5, 7, 0)]
    assert result.skipped["where_false"] == 2                                      # the two SHORT events
    races = result.races
    assert list(races["outcome"]) == ["TIMEOUT", "TIMEOUT"]                         # the 04:00 race's stop came at 06:10
    assert list(races["exit_time"]) == [pd.Timestamp(ny(2026, 1, 5, h, 0)) for h in (5, 8)]   # C3's close
    draws = result.extra["draw_races"]
    assert len(draws) == 6 and (draws["outcome"] == "TIMEOUT").all()               # Tuesday to Friday, same slots
    assert ((draws["exit_time"] - draws["t"]) == pd.Timedelta(minutes=60)).all()
