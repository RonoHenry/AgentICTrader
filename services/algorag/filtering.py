"""
Metadata filtering for AlgoRAG retrieval (Task 10.2).

Builds a Qdrant ``Filter`` from a :class:`~services.algorag.models.RetrievalRequest`
so that vector search is pre-filtered on exact-match payload fields
(instrument, time_window, htf_open_bias, outcome_result) before cosine
similarity ranking runs. All filters beyond ``instrument`` are optional —
missing request parameters simply omit that condition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from qdrant_client.http import models as qmodels

if TYPE_CHECKING:
    from services.algorag.models import RetrievalRequest


def build_qdrant_filter(request: "RetrievalRequest") -> Optional[qmodels.Filter]:
    """Build a Qdrant metadata filter from a retrieval request.

    Always filters on ``instrument`` (required on the request). Adds
    ``time_window`` and ``htf_open_bias`` conditions only when the caller
    supplied them. ``outcome_result`` is filtered when ``outcome_filter`` is
    a non-empty string (e.g. "WIN"); passing ``None`` (or the literal string
    "None") retrieves setups regardless of outcome.

    Args:
        request: The incoming retrieval request.

    Returns:
        A ``qmodels.Filter`` with one ``FieldCondition`` per supplied
        criterion, or ``None`` if the request carries no filterable fields
        at all (defensive fallback — in practice ``instrument`` is always
        present).
    """
    conditions: list[qmodels.FieldCondition] = []

    if request.instrument:
        conditions.append(
            qmodels.FieldCondition(
                key="instrument",
                match=qmodels.MatchValue(value=request.instrument.upper()),
            )
        )

    if request.time_window:
        conditions.append(
            qmodels.FieldCondition(
                key="time_window",
                match=qmodels.MatchValue(value=request.time_window),
            )
        )

    if request.htf_open_bias:
        conditions.append(
            qmodels.FieldCondition(
                key="htf_open_bias",
                match=qmodels.MatchValue(value=request.htf_open_bias),
            )
        )

    outcome_filter = request.outcome_filter
    if outcome_filter and outcome_filter.upper() != "NONE":
        conditions.append(
            qmodels.FieldCondition(
                key="outcome_result",
                match=qmodels.MatchValue(value=outcome_filter.upper()),
            )
        )

    if not conditions:
        return None

    return qmodels.Filter(must=conditions)
