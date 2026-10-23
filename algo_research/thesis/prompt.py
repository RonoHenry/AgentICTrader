"""The procedure sent to the model, and the answer's fixed form (market-narrative Requirement 16.3-16.4).

The procedure is generic ICT, top-down. Nothing from the trader's journal or method blueprint is sent: free
endpoints may log prompts (ND-D4).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from algo_research.thesis.facts import Facts, Rescale

__all__ = ["SYSTEM", "Thesis", "messages_for", "parse_answer"]

SYSTEM = """You are a price-action analyst who reads markets with ICT concepts, top-down: weekly, daily, H4, then H1.
It is the 17:00 New York open of a trading day. Decide the day's thesis from the facts given, or decide there is none.

How to read:
- Each timeframe: where price is now, where it came from, where it is likely to go. Its phase: consolidation,
  expansion, retracement or reversal. A move starts from consolidation into expansion; an expansion is followed by
  a retracement, a consolidation or a reversal.
- The candle lens: the previous candle's range (C1). Did the next candle take one side and close back inside (C2, a
  turtle soup) or close beyond it (displacement)? Bodies against wicks. Premium or discount of the dealing range.
  Fair value gaps (the gap and its midpoint, the CE) and order blocks. Highs, lows and opens not yet taken.
- The draw: price is drawn to liquidity (old highs and lows, equal highs and lows) and to inefficiencies (unfilled
  gaps). A daily candle often makes its false move away from the draw first (manipulation, often in London
  02:00-05:00 or the New York AM 07:00-10:00), then expands toward it.
- The engine's read and the Fractal + POI indicator's live setups are inputs, not orders: weigh them.
- "Neutral" is a valid answer when the timeframes conflict or the draw is unclear. Being wrong costs money; being
  neutral costs nothing.

Use only the facts given; the prices are rescaled (the open is 1000.0, one daily range is 100 points).

Answer with one JSON object and nothing after it:
{"bias": "bullish" | "bearish" | "neutral",
 "draw": the price you expect the day to reach (above 1000 when bullish, below when bearish; null when neutral),
 "invalidation": the price that would prove the thesis wrong before the draw (on the other side of 1000; null when neutral),
 "confidence": "low" | "medium" | "high",
 "reason": "two or three sentences: the draw, the timeframes that agree, what you expect first"}"""


@dataclass(frozen=True)
class Thesis:
    bias: str                       # BULLISH, BEARISH or NO_THESIS
    draw: Optional[float]           # real prices, mapped back
    invalidation: Optional[float]
    confidence: Optional[str]
    reason: str
    draw_scaled: Optional[float]
    invalidation_scaled: Optional[float]

    def as_read(self) -> dict:
        """The form the blind replay's scorer reads."""
        return {"bias": self.bias, "draw": self.draw, "invalidation": self.invalidation}


def messages_for(facts: Facts) -> list[dict]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": facts.text}]


def _last_object(text: str) -> Optional[dict]:
    """The last JSON object in ``text`` (a model may wrap it in a code fence or think aloud first)."""
    text = re.sub(r"```(?:json)?", "", text)
    for start in [m.start() for m in re.finditer(r"\{", text)][::-1]:
        depth = 0
        for k in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            if depth == 0:
                try:
                    obj = json.loads(text[start:k + 1])
                except ValueError:
                    break
                if isinstance(obj, dict) and "bias" in obj:
                    return obj
                break
    return None


def parse_answer(text: str, rs: Rescale) -> Thesis:
    """The answer as a thesis in real prices. Raises ValueError with the reason when it isn't the fixed form."""
    obj = _last_object(text or "")
    if obj is None:
        raise ValueError("no JSON object with a bias")
    bias = str(obj.get("bias", "")).strip().lower()
    reason = str(obj.get("reason") or "")[:1200]
    confidence = str(obj.get("confidence") or "").strip().lower() or None
    if confidence not in (None, "low", "medium", "high"):
        raise ValueError(f"confidence: low, medium or high, not {confidence!r}")
    if bias == "neutral":
        return Thesis("NO_THESIS", None, None, confidence, reason, None, None)
    if bias not in ("bullish", "bearish"):
        raise ValueError(f"bias: bullish, bearish or neutral, not {bias!r}")
    try:
        draw, inval = float(obj["draw"]), float(obj["invalidation"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("a bullish or bearish thesis needs a numeric draw and invalidation") from None
    up = bias == "bullish"
    if (draw <= 1000.0 or inval >= 1000.0) if up else (draw >= 1000.0 or inval <= 1000.0):
        raise ValueError(f"a {bias} thesis needs its draw {'above' if up else 'below'} 1000 and its invalidation on "
                         f"the other side (got draw {draw}, invalidation {inval})")
    return Thesis("BULLISH" if up else "BEARISH", rs.back(draw), rs.back(inval), confidence, reason, draw, inval)
