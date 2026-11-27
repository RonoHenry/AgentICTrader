"""H-AV's reader (algo_research.thesis.weekly): blind facts, the answer's fixed form, and a resumable run that is
scored by the /weekly journal exactly as the trader's calls are."""
import json
import re
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from algo_research.replay.weekly import EVIDENCE, WeeklyApp
from algo_research.thesis import weekly as W

MARKET = "ZZTOPX"


def _days() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("1994-01-03", "1999-12-31")
    close = 80.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.011, len(dates))))
    opn = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.002, len(dates)))
    hi = np.maximum(opn, close) * (1 + np.abs(rng.normal(0, 0.004, len(dates))))
    lo = np.minimum(opn, close) * (1 - np.abs(rng.normal(0, 0.004, len(dates))))
    return pd.DataFrame({"date": dates, "open": opn, "high": hi, "low": lo, "close": close})


@pytest.fixture(scope="module")
def days():
    return _days()


def _app(tmp_path, days):
    return WeeklyApp(tmp_path / "journal", loader=lambda name: days, markets=(MARKET,), reader=False)


def test_the_facts_are_blind(tmp_path, days):
    app = _app(tmp_path, days)
    text = W.facts(app, {}, 0)
    assert MARKET not in text
    assert not re.search(r"\b(19|20)\d\d-\d\d", text), "no dates"
    assert "1000.00" in text and "ALGOMINDDIS MAP" in text and "Untaken liquidity above" in text
    # none of AlgoMindDIS's own verdict
    for word in ("ESTABLISHED", "state", "narrative", "score", "protected level"):
        assert word not in text
    # the D1 rows carry a weekday and four prices, no more
    d1 = text.split("D1, the last")[1].split("ALGOMINDDIS")[0].strip().splitlines()[1:]
    assert d1 and all(re.fullmatch(r"\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)( \d+\.\d\d){4}", r) for r in d1)


def test_parse_call_forms():
    ok = W.parse_call('thinking... {"bias": "bullish", "draw": 1012.5, "protected": 990, "confidence": "high", '
                      '"evidence": ["Displacement", "not a tag"], "reason": "up"}')
    assert (ok.side, ok.draw, ok.protected, ok.confidence, ok.evidence) == ("BULLISH", 1012.5, 990.0, 3,
                                                                          ("Displacement",))
    assert W.parse_call('{"bias": "none", "confidence": "low"}').side == "NONE"
    with pytest.raises(ValueError):
        W.parse_call('{"bias": "bearish", "draw": 1010, "protected": 990, "confidence": "low"}')   # sides swapped
    with pytest.raises(ValueError):
        W.parse_call('{"bias": "bullish", "draw": 1010, "protected": 990}')                       # no confidence
    with pytest.raises(ValueError):
        W.parse_call("no json here")


class _Client:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), 0

    def complete(self, messages, temperature=0.0):
        self.calls += 1
        assert messages[0]["content"] == W.SYSTEM
        return SimpleNamespace(text=self.answers.pop(0) if self.answers else "{}")


def test_run_scores_through_the_weekly_journal_and_resumes(tmp_path, days):
    bull = json.dumps({"bias": "bullish", "draw": 1015, "protected": 985, "confidence": "medium",
                       "evidence": [EVIDENCE[0]], "reason": "r"})
    client = _Client([bull, "garbage", "still garbage", '{"bias": "none", "confidence": "low"}'])
    saved = W.run("fake/model", 0, 3, root=tmp_path, client=client, log=lambda s: None)
    assert saved == 3 and client.calls == 4                       # one retry on the unparsed answer
    recs = sorted(W.app_for("fake/model", tmp_path).records().values(), key=lambda r: r["n"])
    assert [r["side"] for r in recs] == ["BULLISH", "NONE", "NONE"]
    assert recs[0]["score"]["week_hit"] in (0.0, 1.0) and recs[0]["score"]["drift"] is not None
    assert recs[1]["note"].startswith("UNPARSED")
    assert (tmp_path / "fake_model" / "facts" / "0000.txt").is_file()
    again = _Client([])
    assert W.run("fake/model", 0, 3, root=tmp_path, client=again, log=lambda s: None) == 0 and again.calls == 0


def test_verdict_rule():
    assert W.verdict({"sided": 99, "week": {"hit": 0.9, "lo": 0.2}}).startswith("TOO FEW")
    assert W.verdict({"sided": 150, "week": {"hit": 0.58, "lo": 0.01}}) == "PASSES"
    assert W.verdict({"sided": 150, "week": {"hit": 0.56, "lo": 0.01}}) == "FAILS"
    assert W.verdict({"sided": 150, "week": {"hit": 0.60, "lo": -0.01}}) == "FAILS"
