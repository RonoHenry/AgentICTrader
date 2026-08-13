"""
HTF directional bias classification.

For D1/W1/MN1, `reference_open` is simply the open of that timeframe's most
recent candle — the engine trusts its upstream feed to have already bucketed
those candles on the correct session boundary (NY midnight for D1, Sunday
18:00 EST for W1, calendar month for MN1), since a single already-formed
candle carries no metadata about *why* it started when it did. `current_price`
is one shared value (the latest close on the finest timeframe supplied) so
every timeframe's bias reflects the same live price against a different
opening anchor.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from liquidity_engine.models import BiasDirection, Candle, HTFBias, Timeframe

# Within this band (as a fraction of reference_open), direction is NEUTRAL.
_NEUTRAL_BAND_PCT: float = 0.0001

# Beyond this band (as a fraction of reference_open), price counts as "deep"
# premium/discount relative to the reference open. A first-pass default,
# not backtest-derived — see EXPANSION_WICK_RATIO_MAX for the same convention.
_DEEP_BAND_PCT: float = 0.005


class HTFBiasClassifier:
    """Classifies directional bias per timeframe against each timeframe's opening anchor."""

    def classify(
        self, candles_by_tf: Dict[Timeframe, List[Candle]], current_price: float
    ) -> Dict[Timeframe, HTFBias]:
        bias: Dict[Timeframe, HTFBias] = {}
        midnight_reference = self._midnight_reference(candles_by_tf)
        for tf, candles in candles_by_tf.items():
            if not candles:
                continue
            reference_open, reference_open_time = self._get_reference_open(candles)
            bias[tf] = self._build_bias(
                tf, reference_open, reference_open_time, current_price, midnight_reference
            )
        return bias

    def _midnight_reference(self, candles_by_tf: Dict[Timeframe, List[Candle]]) -> float | None:
        """D1's reference open doubles as the 'midnight reference' other timeframes compare against."""
        d1_candles = candles_by_tf.get(Timeframe.D1)
        if not d1_candles:
            return None
        return d1_candles[-1].open

    def _get_reference_open(self, candles: List[Candle]) -> tuple[float, datetime]:
        latest = candles[-1]
        return latest.open, latest.timestamp

    def _build_bias(
        self,
        tf: Timeframe,
        reference_open: float,
        reference_open_time: datetime,
        current_price: float,
        midnight_reference: float | None,
    ) -> HTFBias:
        distance_from_open = current_price - reference_open
        distance_pct = distance_from_open / reference_open if reference_open != 0 else 0.0

        if abs(distance_pct) <= _NEUTRAL_BAND_PCT:
            direction = BiasDirection.NEUTRAL
        elif current_price > reference_open:
            direction = BiasDirection.BULLISH
        else:
            direction = BiasDirection.BEARISH

        is_deep_premium = distance_pct >= _DEEP_BAND_PCT
        is_deep_discount = distance_pct <= -_DEEP_BAND_PCT

        return HTFBias(
            timeframe=tf,
            direction=direction,
            reference_open=reference_open,
            reference_open_time=reference_open_time,
            current_price=current_price,
            distance_from_open=distance_from_open,
            distance_pct=distance_pct,
            is_deep_premium=is_deep_premium,
            is_deep_discount=is_deep_discount,
            midnight_reference=midnight_reference,
            news_reference=None,
        )
