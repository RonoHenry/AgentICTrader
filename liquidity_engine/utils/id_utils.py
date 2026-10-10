"""
Deterministic identifier generation.

The engine must be stateless and fully deterministic (Requirement 1.2 / Property 1):
identical candle input must produce an identical output on every call. Random
UUIDs (`uuid4`) would break that guarantee, so every `*_id` field across the
package is derived from its own content via `uuid5` against a fixed namespace —
still a valid UUID string, but reproducible.
"""
from __future__ import annotations

from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

_NAMESPACE = uuid5(NAMESPACE_URL, "liquidity_engine")


def deterministic_id(*parts: object) -> str:
    """A stable UUID string derived from `parts`; identical parts always yield the same id."""
    return _uuid_for("|".join(repr(p) for p in parts))


@lru_cache(maxsize=1 << 18)
def _uuid_for(key: str) -> str:
    # Consecutive analyses share most of their window, so most ids repeat;
    # uuid5 is a pure function of the key.
    return str(uuid5(_NAMESPACE, key))
