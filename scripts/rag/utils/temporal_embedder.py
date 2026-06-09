"""
Temporal Embedder — encodes a UTC timestamp into a 16-dimensional cyclical vector.

Cyclical sin/cos encoding captures time periodicity without ordinal bias, which
prevents the model from seeing "hour 23" and "hour 0" as far apart.

Usage:
    from scripts.rag.utils.temporal_embedder import TemporalEmbedder

    emb = TemporalEmbedder()
    vector = emb.encode(datetime(2024, 3, 15, 9, 15, tzinfo=timezone.utc))
    # → np.ndarray of shape (16,), dtype float64
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import numpy as np


class TemporalEmbedder:
    """Encodes a UTC timestamp into a 16-dimensional cyclical embedding.

    Encoding layout
    ---------------
    dim 0: sin(2π * hour / 24)
    dim 1: cos(2π * hour / 24)
    dim 2: sin(2π * day_of_week / 5)
    dim 3: cos(2π * day_of_week / 5)
    dim 4: sin(2π * month / 12)
    dim 5: cos(2π * month / 12)
    dims 6–15: 0.0  (reserved for future features)
    """

    DIM: int = 16

    def encode(self, timestamp: datetime) -> np.ndarray:
        """
        Encode a timestamp into a 16-dim cyclical vector.

        Args:
            timestamp: datetime object.
                       Naive → assumed UTC.
                       Aware  → converted to UTC before encoding.

        Returns:
            np.ndarray of shape (16,) with dtype float64.
            Dims 0-5: sin/cos encodings for hour, day-of-week, month.
            Dims 6-15: zeros (reserved).
        """
        utc_ts = self._to_utc(timestamp)

        hour = utc_ts.hour
        dow = utc_ts.weekday()  # 0=Monday … 6=Sunday
        month = utc_ts.month    # 1–12

        vec = np.zeros(self.DIM, dtype=np.float64)

        # Hour cyclical encoding
        vec[0] = math.sin(2.0 * math.pi * hour / 24.0)
        vec[1] = math.cos(2.0 * math.pi * hour / 24.0)

        # Day-of-week cyclical encoding (period 5 per spec)
        vec[2] = math.sin(2.0 * math.pi * dow / 5.0)
        vec[3] = math.cos(2.0 * math.pi * dow / 5.0)

        # Month cyclical encoding
        vec[4] = math.sin(2.0 * math.pi * month / 12.0)
        vec[5] = math.cos(2.0 * math.pi * month / 12.0)

        # dims 6–15 remain 0.0 (reserved)

        return vec

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_utc(timestamp: datetime) -> datetime:
        """Normalise a datetime to UTC.

        * Naive datetime  → assumed to already be UTC (attach UTC tzinfo).
        * Aware datetime  → convert to UTC via astimezone().
        """
        if timestamp.tzinfo is None:
            # Naive — assume UTC
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)
