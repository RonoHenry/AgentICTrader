"""
Regime Classifier model package.

This package contains the regime classification model that classifies market regime into:
- TRENDING_BULLISH
- TRENDING_BEARISH
- RANGING
- BREAKOUT
- NEWS_DRIVEN

The classifier uses XGBoost multi-class classification with features from:
- HTF projection features (HTF open/high/low, bias, proximity)
- Candle structure features (body %, wick %, close position)
- Zone features (BOS, CHoCH, FVG, liquidity sweep, swing distances)
- Session features (time window, narrative phase, killzone flags)

**Implements: Task 20 - Train and validate Regime Classifier**
"""

__all__ = ["train"]
