"""
Diversity filtering for AlgoRAG retrieval (Task 10.5).

Limits the number of retrieved setups that share the same calendar day so a
single volatile session can't dominate the top-N results with near-duplicate
entries. Setups are assumed to already be sorted by relevance (e.g. by
``final_score`` after re-ranking) — within each day, the highest-ranked
entries are kept and the rest are dropped, preserving overall order.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from services.algorag.models import SimilarSetup


def apply_diversity_filter(
    setups: "List[SimilarSetup]", max_per_day: int = 3
) -> "List[SimilarSetup]":
    """Keep at most ``max_per_day`` setups per calendar day.

    Args:
        setups: Setups already ordered by relevance (most relevant first).
        max_per_day: Maximum number of setups allowed from the same
            (UTC) calendar day. Must be a positive integer to have any
            filtering effect.

    Returns:
        A new list preserving the input order, with lower-ranked setups
        beyond ``max_per_day`` for a given day removed.
    """
    if not setups or max_per_day <= 0:
        return list(setups)

    counts: dict = defaultdict(int)
    diverse: List["SimilarSetup"] = []

    for setup in setups:
        day_key = setup.timestamp.date()
        if counts[day_key] < max_per_day:
            diverse.append(setup)
            counts[day_key] += 1

    return diverse
