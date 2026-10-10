"""Partner features: what a correlated instrument had done by the same t (SMT).

SMT divergence (update 2026-10c, Requirement 16): one instrument takes a
level while its correlated partner fails to take its own. research.toml
names the pairs (AR-D12, EURUSD with GBPUSD). For each row of a paired
instrument, these columns copy the partner's facts from the partner's row at
the same t. That row's features are known at t (Property 1), so nothing is
read ahead.

A fact is null when the partner has no row at t (a data gap), when it isn't
known there (the Asian range before midnight), or, for the candle ranges,
when the partner's C2 is a different candle from the row's own. Every column
is null for an instrument without a partner.

    tables = partner_features({"EURUSD": eur, "GBPUSD": gbp, "XAUUSD": xau}, (("EURUSD", "GBPUSD"),))

The columns are joined after the cache (dataset.py): they cost one merge.

Validates: Requirement 16.2 (.kiro/specs/algo-research/requirements.md)
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from algo_research.features.market import CRT_TIMEFRAMES, Column

__all__ = ["PARTNER_COLUMNS", "partner_features"]

PARTNER_COLUMNS: dict[str, Column] = {
    "partner": Column("the instrument paired with this one in research.toml [smt]; null without one", "name",
                      "always"),
    "partner_asia_high_raided": Column(
        "the partner's asia_high_raided_at is set at t; null when the partner has no row at t or its Asian "
        "range isn't known", "bool", "t"),
    "partner_asia_low_raided": Column(
        "the partner's asia_low_raided_at is set at t; null when the partner has no row at t or its Asian "
        "range isn't known", "bool", "t"),
}
for _name, _tf in CRT_TIMEFRAMES.items():
    for _side, _test in (("high", "high > its C1's high"), ("low", "low < its C1's low")):
        PARTNER_COLUMNS[f"partner_crt_{_name}_swept_{_side}"] = Column(
            f"the partner's {_tf.value} C2 {_test}; null when its crt_{_name}_at differs from this row's, or it "
            f"has no C1", "bool", "t")


def partner_features(markets: Mapping[str, pd.DataFrame], pairs: Sequence[tuple[str, str]]) -> dict[str, pd.DataFrame]:
    """Each instrument's table with PARTNER_COLUMNS added (same index, same rows)."""
    partners = {**{a: b for a, b in pairs}, **{b: a for a, b in pairs}}
    out = {}
    for instrument, table in markets.items():
        partner = partners.get(instrument)
        facts = _facts(markets[partner]) if partner in markets else None
        out[instrument] = _join(table, partner, facts)
    return out


def _known(flag: np.ndarray, known: np.ndarray) -> pd.Series:
    values = pd.array(flag, dtype="boolean")
    values[~known] = pd.NA
    return values


def _facts(table: pd.DataFrame) -> pd.DataFrame:
    """The partner's own facts at each of its rows."""
    facts = pd.DataFrame({"t": table["t"].to_numpy()})
    for side in ("high", "low"):
        known = table[f"asia_{side}"].notna().to_numpy()
        facts[f"partner_asia_{side}_raided"] = _known(table[f"asia_{side}_raided_at"].notna().to_numpy(), known)
    for name in CRT_TIMEFRAMES:
        c1_high, c1_low = (table[f"crt_{name}_c1_{s}"].to_numpy(dtype=float) for s in ("high", "low"))
        c2_high, c2_low = (table[f"crt_{name}_c2_{s}"].to_numpy(dtype=float) for s in ("high", "low"))
        known = ~np.isnan(c1_high) & ~np.isnan(c2_high)
        with np.errstate(invalid="ignore"):
            facts[f"partner_crt_{name}_swept_high"] = _known(c2_high > c1_high, known)
            facts[f"partner_crt_{name}_swept_low"] = _known(c2_low < c1_low, known)
        facts[f"_crt_{name}_at"] = table[f"crt_{name}_at"].to_numpy()
    return facts


def _join(table: pd.DataFrame, partner, facts) -> pd.DataFrame:
    out = table.copy()
    if facts is None:
        out["partner"] = pd.Series(None, index=out.index, dtype=object)
        for name in list(PARTNER_COLUMNS)[1:]:
            out[name] = pd.array([pd.NA] * len(out), dtype="boolean")
        return out
    joined = pd.DataFrame({"t": table["t"].to_numpy()}).merge(facts, on="t", how="left", validate="one_to_one")
    out["partner"] = partner
    for name in ("partner_asia_high_raided", "partner_asia_low_raided"):
        out[name] = joined[name].array
    for name in CRT_TIMEFRAMES:
        same = np.asarray(pd.DatetimeIndex(joined[f"_crt_{name}_at"]) == pd.DatetimeIndex(table[f"crt_{name}_at"]))
        for side in ("high", "low"):
            values = joined[f"partner_crt_{name}_swept_{side}"].array.copy()
            values[~same] = pd.NA
            out[f"partner_crt_{name}_swept_{side}"] = values
    return out
