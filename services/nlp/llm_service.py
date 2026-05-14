"""
LLM macro event summariser and trade reasoning generator for AgentICTrader.

Provides two main capabilities:
1. summarise_macro_event(event) — summarises a macro economic event using Claude API
2. generate_trade_reasoning(setup) — generates structured trade reasoning using the
   3-question narrative framework (where has price come from / where is it now /
   where is it likely to go)

Claude (Anthropic) is the primary LLM. If the Claude API is unavailable, both
functions fall back to template-based reasoning using get_narrative_context().

Usage::

    service = LLMService(anthropic_api_key="YOUR_KEY")
    summary = await service.summarise_macro_event(event)
    reasoning = await service.generate_trade_reasoning(setup)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Anthropic import — graceful degradation if not installed
# ---------------------------------------------------------------------------
try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ANTHROPIC_AVAILABLE = False
    anthropic = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_MODEL = "claude-3-5-sonnet-20241022"

# Narrative phase → human-readable description
_PHASE_DESCRIPTIONS: dict[str, str] = {
    "ACCUMULATION": "accumulation phase (liquidity building)",
    "MANIPULATION": "manipulation phase (stop hunt / liquidity sweep)",
    "EXPANSION": "expansion/delivery phase",
    "DISTRIBUTION": "distribution phase (position squaring)",
    "TRANSITION": "transition phase (NY midnight reference)",
    "OFF": "off-hours",
}

# Time window → human-readable label
_WINDOW_LABELS: dict[str, str] = {
    "ASIAN_RANGE": "Asian Range (20:00–22:00 NY)",
    "TRUE_DAY_OPEN": "True Day Open (00:00–01:00 NY)",
    "LONDON_KILLZONE": "London Killzone (02:00–05:00 NY)",
    "LONDON_SILVER_BULLET": "London Silver Bullet (03:00–04:00 NY)",
    "NY_AM_KILLZONE": "NY AM Killzone (07:00–10:00 NY)",
    "NY_AM_SILVER_BULLET": "NY AM Silver Bullet (10:00–11:00 NY)",
    "LONDON_CLOSE": "London Close (10:00–12:00 NY)",
    "NY_PM_KILLZONE": "NY PM Killzone (13:30–16:00 NY)",
    "NY_PM_SILVER_BULLET": "NY PM Silver Bullet (14:00–15:00 NY)",
    "NEWS_WINDOW": "News Window (08:00–09:00 NY)",
    "DAILY_CLOSE": "Daily Close (17:00–18:00 NY)",
    "OFF_HOURS": "Off-Hours",
}


# ---------------------------------------------------------------------------
# LLMService
# ---------------------------------------------------------------------------


class LLMService:
    """
    LLM-powered macro event summariser and trade reasoning generator.

    Uses Claude (Anthropic) as the primary LLM with automatic fallback to
    template-based reasoning when the API is unavailable or returns an error.

    Args:
        anthropic_api_key: Anthropic API key. If empty or None, the service
            operates in template-only mode (no Claude calls).
        claude_model: Claude model identifier to use.
        max_tokens: Maximum tokens for Claude responses.
    """

    def __init__(
        self,
        anthropic_api_key: str = "",
        claude_model: str = CLAUDE_MODEL,
        max_tokens: int = 512,
    ) -> None:
        self._api_key = anthropic_api_key
        self._claude_model = claude_model
        self._max_tokens = max_tokens
        self._client: Optional[object] = None

        if _ANTHROPIC_AVAILABLE and anthropic_api_key:
            try:
                self._client = anthropic.Anthropic(api_key=anthropic_api_key)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to initialise Anthropic client: %s", exc)
                self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def summarise_macro_event(self, event: dict) -> str:
        """Summarise a macro economic event in plain English.

        Attempts to use Claude to produce a concise, trader-focused summary.
        Falls back to a template-based summary if Claude is unavailable.

        Args:
            event: Dict with at least ``event_name`` and optionally
                ``currency``, ``impact``, ``actual``, ``forecast``,
                ``previous``, ``event_time``.

        Returns:
            A plain-English summary string (never empty).
        """
        if self._client is not None:
            try:
                return await self._summarise_with_claude(event)
            except Exception as exc:
                logger.warning(
                    "Claude summarise_macro_event failed (%s) — using template fallback",
                    exc,
                )

        return self._summarise_template(event)

    async def generate_trade_reasoning(self, setup: dict) -> str:
        """Generate structured trade reasoning for a detected setup.

        The reasoning is structured around the 3-question narrative framework:
        1. Where has price come from? (HTF context, PD arrays swept/respected)
        2. Where is it now? (time window, price vs reference opens)
        3. Where is it likely to go? (nearest liquidity pool or imbalance)

        Attempts to use Claude for richer, context-aware prose. Falls back to
        template-based reasoning (via :func:`get_narrative_context`) if Claude
        is unavailable.

        Args:
            setup: Dict containing setup context. Expected keys (all optional
                but used when present):

                - ``instrument`` (str)
                - ``direction`` (str): "BULLISH" | "BEARISH"
                - ``htf_open_bias`` (str): "BULLISH" | "BEARISH" | "NEUTRAL"
                - ``htf_open`` (float)
                - ``htf_high`` (float)
                - ``htf_low`` (float)
                - ``time_window`` (str)
                - ``narrative_phase`` (str)
                - ``price_vs_daily_open`` (str): "ABOVE" | "BELOW" | "AT"
                - ``price_vs_weekly_open`` (str)
                - ``price_vs_true_day_open`` (str)
                - ``patterns`` (list[str])
                - ``confidence_score`` (float)
                - ``entry_price`` (float)
                - ``sl_price`` (float)
                - ``tp_price`` (float)
                - ``swing_high`` (float)
                - ``swing_low`` (float)
                - ``fvg_present`` (bool)
                - ``session_sweep_time`` (str): e.g. "03:15 NY"
                - ``session_sweep_level`` (str): e.g. "Asian range low"

        Returns:
            A structured reasoning string (never empty).
        """
        if self._client is not None:
            try:
                return await self._reason_with_claude(setup)
            except Exception as exc:
                logger.warning(
                    "Claude generate_trade_reasoning failed (%s) — using template fallback",
                    exc,
                )

        return self._reason_template(setup)

    # ------------------------------------------------------------------
    # Claude implementations
    # ------------------------------------------------------------------

    async def _summarise_with_claude(self, event: dict) -> str:
        """Call Claude to summarise a macro event."""
        event_name = event.get("event_name", "Unknown event")
        currency = event.get("currency", "")
        impact = event.get("impact", "")
        actual = event.get("actual", "N/A")
        forecast = event.get("forecast", "N/A")
        previous = event.get("previous", "N/A")
        event_time = event.get("event_time", "")

        prompt = (
            f"You are a professional FX/indices trader. Summarise the following "
            f"macro economic event in 1–2 concise sentences, focusing on the "
            f"likely market impact and directional bias for {currency or 'affected instruments'}.\n\n"
            f"Event: {event_name}\n"
            f"Currency: {currency}\n"
            f"Impact: {impact}\n"
            f"Actual: {actual}\n"
            f"Forecast: {forecast}\n"
            f"Previous: {previous}\n"
            f"Time: {event_time}\n\n"
            f"Summary:"
        )

        message = self._client.messages.create(  # type: ignore[union-attr]
            model=self._claude_model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    async def _reason_with_claude(self, setup: dict) -> str:
        """Call Claude to generate structured trade reasoning."""
        instrument = setup.get("instrument", "Unknown")
        direction = setup.get("direction", "")
        htf_bias = setup.get("htf_open_bias", "NEUTRAL")
        htf_open = setup.get("htf_open", 0.0)
        htf_high = setup.get("htf_high", 0.0)
        htf_low = setup.get("htf_low", 0.0)
        time_window = setup.get("time_window", "OFF_HOURS")
        narrative_phase = setup.get("narrative_phase", "OFF")
        price_vs_daily = setup.get("price_vs_daily_open", "")
        price_vs_weekly = setup.get("price_vs_weekly_open", "")
        price_vs_true_day = setup.get("price_vs_true_day_open", "")
        patterns = setup.get("patterns", [])
        confidence = setup.get("confidence_score", 0.0)
        entry = setup.get("entry_price", 0.0)
        sl = setup.get("sl_price", 0.0)
        tp = setup.get("tp_price", 0.0)
        swing_high = setup.get("swing_high")
        swing_low = setup.get("swing_low")
        fvg_present = setup.get("fvg_present", False)
        sweep_time = setup.get("session_sweep_time", "")
        sweep_level = setup.get("session_sweep_level", "")

        window_label = _WINDOW_LABELS.get(time_window, time_window)
        phase_desc = _PHASE_DESCRIPTIONS.get(narrative_phase, narrative_phase)

        prompt = (
            f"You are a professional ICT-trained trader. Generate structured trade "
            f"reasoning for the following setup using the 3-question framework.\n\n"
            f"Instrument: {instrument}\n"
            f"Direction: {direction}\n"
            f"HTF Open Bias: {htf_bias} (HTF open: {htf_open}, high: {htf_high}, low: {htf_low})\n"
            f"Time Window: {window_label} — {phase_desc}\n"
            f"Price vs Daily Open: {price_vs_daily}\n"
            f"Price vs Weekly Open: {price_vs_weekly}\n"
            f"Price vs True Day Open: {price_vs_true_day}\n"
            f"Patterns detected: {', '.join(patterns) if patterns else 'None'}\n"
            f"Confidence score: {confidence:.2f}\n"
            f"Entry: {entry}, SL: {sl}, TP: {tp}\n"
            f"Swing High: {swing_high}, Swing Low: {swing_low}\n"
            f"FVG Present: {fvg_present}\n"
            f"Session sweep: {sweep_level} at {sweep_time}\n\n"
            f"Answer these 3 questions in 2–4 sentences total:\n"
            f"1. Where has price come from? (HTF context, PD arrays swept/respected)\n"
            f"2. Where is it now? (time window phase, price vs reference opens)\n"
            f"3. Where is it likely to go? (nearest liquidity pool or imbalance)\n\n"
            f"Entry bias rule: "
            + (
                "Bullish — note price is below session open (manipulation wick down expected before expansion up)."
                if direction == "BULLISH"
                else "Bearish — note price is above session open (manipulation wick up expected before expansion down)."
                if direction == "BEARISH"
                else "Neutral — describe the likely next move."
            )
            + "\n\nReasoning:"
        )

        message = self._client.messages.create(  # type: ignore[union-attr]
            model=self._claude_model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    # ------------------------------------------------------------------
    # Template fallbacks
    # ------------------------------------------------------------------

    def _summarise_template(self, event: dict) -> str:
        """Template-based macro event summary (no LLM required)."""
        event_name = event.get("event_name", "Unknown event")
        currency = event.get("currency", "")
        impact = event.get("impact", "")
        actual = event.get("actual")
        forecast = event.get("forecast")
        previous = event.get("previous")

        parts: list[str] = []

        # Impact label
        impact_label = f"{impact} impact" if impact else "Economic"
        currency_label = f" ({currency})" if currency else ""
        parts.append(f"{impact_label} event{currency_label}: {event_name}.")

        # Actual vs forecast
        if actual is not None and forecast is not None:
            try:
                actual_f = float(actual)
                forecast_f = float(forecast)
                if actual_f > forecast_f:
                    bias = "beat expectations"
                    direction_hint = "bullish" if currency not in ("USD",) else "hawkish"
                elif actual_f < forecast_f:
                    bias = "missed expectations"
                    direction_hint = "bearish" if currency not in ("USD",) else "dovish"
                else:
                    bias = "met expectations"
                    direction_hint = "neutral"
                parts.append(
                    f"Actual {actual} vs forecast {forecast} — {bias} ({direction_hint} bias)."
                )
            except (TypeError, ValueError):
                parts.append(f"Actual: {actual}, Forecast: {forecast}.")
        elif actual is not None:
            parts.append(f"Actual: {actual}.")
            if previous is not None:
                parts.append(f"Previous: {previous}.")

        return " ".join(parts)

    def _reason_template(self, setup: dict) -> str:
        """Template-based trade reasoning using get_narrative_context().

        Implements the 3-question framework directly without an LLM.
        """
        # Import here to avoid circular imports at module level
        from ml.features.session_features import get_narrative_context, TimeFeatures

        instrument = setup.get("instrument", "Unknown")
        direction = setup.get("direction", "")
        htf_bias = setup.get("htf_open_bias", "NEUTRAL")
        htf_open = setup.get("htf_open", 0.0)
        htf_high = setup.get("htf_high", 0.0)
        htf_low = setup.get("htf_low", 0.0)
        time_window = setup.get("time_window", "OFF_HOURS")
        narrative_phase = setup.get("narrative_phase", "OFF")
        price_vs_daily = setup.get("price_vs_daily_open")
        price_vs_weekly = setup.get("price_vs_weekly_open")
        price_vs_true_day = setup.get("price_vs_true_day_open")
        patterns = setup.get("patterns", [])
        confidence = setup.get("confidence_score", 0.0)
        entry = setup.get("entry_price", 0.0)
        sl = setup.get("sl_price", 0.0)
        tp = setup.get("tp_price", 0.0)
        swing_high = setup.get("swing_high")
        swing_low = setup.get("swing_low")
        fvg_present = setup.get("fvg_present", False)
        sweep_time = setup.get("session_sweep_time", "")
        sweep_level = setup.get("session_sweep_level", "")

        # Build TimeFeatures for get_narrative_context
        time_window_weight = _TIME_WINDOW_WEIGHTS.get(time_window, 0.1)
        is_killzone = time_window in {
            "LONDON_KILLZONE", "LONDON_SILVER_BULLET",
            "NY_AM_KILLZONE", "NY_AM_SILVER_BULLET",
            "NY_PM_KILLZONE", "NY_PM_SILVER_BULLET",
        }
        time_features = TimeFeatures(
            time_window=time_window,
            narrative_phase=narrative_phase,
            time_window_weight=time_window_weight,
            is_killzone=is_killzone,
            is_high_probability_window=time_window_weight >= 0.7,
            price_vs_daily_open=price_vs_daily,
            price_vs_weekly_open=price_vs_weekly,
            price_vs_true_day_open=price_vs_true_day,
        )

        htf_features = {
            "htf_open_bias": htf_bias,
            "htf_open": htf_open,
            "htf_high": htf_high,
            "htf_low": htf_low,
        }

        zone_features = {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "fvg_present": fvg_present,
        }

        # Base narrative from get_narrative_context
        base_narrative = get_narrative_context(time_features, htf_features, zone_features)

        # Enrich with sweep context (Q1: where has price come from?)
        parts: list[str] = []

        if sweep_level and sweep_time:
            parts.append(
                f"Price swept the {sweep_level} at {sweep_time} "
                f"({_WINDOW_LABELS.get(time_window, time_window)} — "
                f"{_PHASE_DESCRIPTIONS.get(narrative_phase, narrative_phase)})."
            )
        else:
            parts.append(base_narrative)

        # HTF open bias (Q1 continuation)
        if sweep_level and sweep_time:
            parts.append(f"HTF open bias is {htf_bias}.")

        # Price vs reference opens (Q2: where is it now?)
        if price_vs_true_day:
            fvg_note = " with a bullish FVG at discount" if (fvg_present and htf_bias == "BULLISH") else (
                " with a bearish FVG at premium" if (fvg_present and htf_bias == "BEARISH") else ""
            )
            parts.append(
                f"Price is {price_vs_true_day.lower()} the True Day Open{fvg_note}."
            )

        # Patterns
        if patterns:
            parts.append(f"Patterns: {', '.join(patterns)}.")

        # Entry bias (Q2 continuation)
        if direction == "BULLISH":
            parts.append(
                "Price is below session open — expecting manipulation wick down before expansion up."
            )
        elif direction == "BEARISH":
            parts.append(
                "Price is above session open — expecting manipulation wick up before expansion down."
            )

        # Q3: where is it likely to go?
        if htf_bias == "BULLISH":
            target = htf_high
            target_label = "HTF high"
            if swing_high:
                target = swing_high
                target_label = "swing high"
            window_label = _WINDOW_LABELS.get("NY_AM_KILLZONE", "NY AM Killzone")
            parts.append(
                f"Expecting expansion higher into the {window_label} "
                f"toward {target_label} at {target:.5f}."
            )
        elif htf_bias == "BEARISH":
            target = htf_low
            target_label = "HTF low"
            if swing_low:
                target = swing_low
                target_label = "swing low"
            window_label = _WINDOW_LABELS.get("NY_AM_KILLZONE", "NY AM Killzone")
            parts.append(
                f"Expecting expansion lower into the {window_label} "
                f"toward {target_label} at {target:.5f}."
            )

        # Confidence and trade plan
        if confidence > 0:
            parts.append(f"Confidence: {confidence:.0%}.")
        if entry and sl and tp:
            r_ratio = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 1e-9 else 0.0
            parts.append(
                f"Entry: {entry}, SL: {sl}, TP: {tp} ({r_ratio:.1f}R)."
            )

        return " ".join(parts)


# ---------------------------------------------------------------------------
# Time window weights (mirrors session_features.py — kept local to avoid
# circular imports at module level)
# ---------------------------------------------------------------------------

_TIME_WINDOW_WEIGHTS: dict[str, float] = {
    "LONDON_SILVER_BULLET": 1.0,
    "NY_AM_SILVER_BULLET": 1.0,
    "NY_PM_SILVER_BULLET": 1.0,
    "LONDON_KILLZONE": 0.9,
    "NY_AM_KILLZONE": 0.9,
    "NY_PM_KILLZONE": 0.9,
    "NEWS_WINDOW": 0.8,
    "TRUE_DAY_OPEN": 0.7,
    "LONDON_CLOSE": 0.5,
    "ASIAN_RANGE": 0.3,
    "DAILY_CLOSE": 0.2,
    "OFF_HOURS": 0.1,
}
