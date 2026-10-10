"""
RAG-enhanced prompt templates for LLM trade reasoning.

This module provides prompt templates that incorporate historical similar setups
from AlgoRAG into the LLM reasoning process.

Usage:
    template = RAGPromptTemplate()
    prompt = template.build_reasoning_prompt(setup, similar_setups)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


class RAGPromptTemplate:
    """Builds RAG-enhanced prompts for trade reasoning."""
    
    def build_reasoning_prompt(self, setup: Dict[str, Any], similar_setups: List[Any]) -> str:
        """
        Build a prompt that includes similar historical setups for context.
        
        Args:
            setup: Current trading setup
            similar_setups: List of similar historical setups from RAG
            
        Returns:
            Complete prompt string for Claude
        """
        # Extract setup details
        instrument = setup.get("instrument", "Unknown")
        direction = setup.get("direction", "")
        htf_bias = setup.get("htf_open_bias", "NEUTRAL")
        htf_open = setup.get("htf_open", 0.0)
        htf_high = setup.get("htf_high", 0.0)
        htf_low = setup.get("htf_low", 0.0)
        time_window = setup.get("time_window", "OFF_HOURS")
        narrative_phase = setup.get("narrative_phase", "OFF")
        price_vs_daily = setup.get("price_vs_daily_open", "")
        patterns = setup.get("patterns", [])
        confidence = setup.get("confidence_score", 0.0)
        entry = setup.get("entry_price", 0.0)
        sl = setup.get("sl_price", 0.0)
        tp = setup.get("tp_price", 0.0)
        
        # Build setup description
        setup_description = self._build_setup_description(setup)
        
        # Build historical examples section
        historical_section = self._build_historical_section(similar_setups)
        
        # Build main prompt
        prompt = f"""You are a professional ICT-trained trader. Generate structured trade reasoning for the following setup using the 3-question framework.

{setup_description}

{historical_section}

Answer these 3 questions using both the current setup and historical precedent:
1. Where has price come from? (HTF context, PD arrays swept/respected, what similar setups show)
2. Where is it now? (time window phase, price vs reference opens, comparison to historical patterns)
3. Where is it likely to go? (nearest liquidity pool or imbalance, what similar outcomes suggest)

Entry bias rule: """
        
        if direction == "BULLISH":
            prompt += "Bullish — note price is below session open (manipulation wick down expected before expansion up)."
        elif direction == "BEARISH":
            prompt += "Bearish — note price is above session open (manipulation wick up expected before expansion down)."
        else:
            prompt += "Neutral — describe the likely next move."
            
        prompt += """

Reasoning:"""
        
        return prompt
    
    def _build_setup_description(self, setup: Dict[str, Any]) -> str:
        """Build the current setup description section."""
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
        
        # Map time windows and phases to human-readable labels
        window_labels = {
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
        
        phase_descriptions = {
            "ACCUMULATION": "accumulation phase (liquidity building)",
            "MANIPULATION": "manipulation phase (stop hunt / liquidity sweep)",
            "EXPANSION": "expansion/delivery phase",
            "DISTRIBUTION": "distribution phase (position squaring)",
            "TRANSITION": "transition phase (NY midnight reference)",
            "OFF": "off-hours",
        }
        
        window_label = window_labels.get(time_window, time_window)
        phase_desc = phase_descriptions.get(narrative_phase, narrative_phase)
        
        return f"""CURRENT SETUP:
Instrument: {instrument}
Direction: {direction}
HTF Open Bias: {htf_bias} (HTF open: {htf_open}, high: {htf_high}, low: {htf_low})
Time Window: {window_label} — {phase_desc}
Price vs Daily Open: {price_vs_daily}
Price vs Weekly Open: {price_vs_weekly}
Price vs True Day Open: {price_vs_true_day}
Patterns detected: {', '.join(patterns) if patterns else 'None'}
Confidence score: {confidence:.2f}
Entry: {entry}, SL: {sl}, TP: {tp}
Swing High: {swing_high}, Swing Low: {swing_low}
FVG Present: {fvg_present}"""
    
    def _build_historical_section(self, similar_setups: List[Any]) -> str:
        """Build the historical similar setups section."""
        if not similar_setups:
            return "HISTORICAL CONTEXT:\nNo similar historical setups found."

        section_lines = ["SIMILAR HISTORICAL SETUPS:"]

        for i, similar in enumerate(similar_setups[:3], 1):  # Limit to top 3
            fields = normalize_similar_setup(similar)
            similarity = to_float(fields.get("similarity_score")) or 0.0

            trade_id = fields.get("trade_id") or "Unknown"
            timestamp = fields.get("timestamp") or ""
            narrative = fields.get("narrative") or "No description available"
            outcome = fields.get("outcome_result") or "UNKNOWN"
            r_multiple = to_float(fields.get("outcome_r_multiple"))
            r_label = f"{r_multiple:.1f}R" if r_multiple is not None else "N/A"

            section_lines.append(
                f"{i}. [{trade_id}] {_format_timestamp(timestamp)} ({similarity:.0%} similarity)\n"
                f"   Setup: {narrative}\n"
                f"   Outcome: {outcome} ({r_label})"
            )

        return "\n".join(section_lines)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def normalize_similar_setup(item: Any) -> Dict[str, Any]:
    """Flatten one retrieved similar setup into a single dict of fields.

    The AlgoRAG ``POST /rag/retrieve`` contract
    (``services/algorag/models.py::SimilarSetup``) returns every similar setup
    FLAT -- ``trade_id``, ``timestamp``, ``narrative``, ``outcome_result``,
    ``outcome_r_multiple``, ``similarity_score`` and ``final_score`` are all
    top-level keys. An older in-repo shape nests the trade fields under a
    ``"setup"`` key with the scores beside it. Formatters that only read the
    nested shape silently drop the trade id, narrative and outcome of real
    AlgoRAG results, so every formatter goes through this function, which
    accepts both shapes (plus pydantic models such as the agent's
    ``SimilarSetup``). Top-level keys win over nested ones.
    """
    if hasattr(item, "model_dump"):
        item = item.model_dump()
    if not isinstance(item, dict):
        return {}
    nested = item.get("setup")
    fields: Dict[str, Any] = dict(nested) if isinstance(nested, dict) else {}
    fields.update({k: v for k, v in item.items() if k != "setup"})
    return fields


def to_float(value: Any) -> Optional[float]:
    """``float(value)``, or None when *value* is missing or not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_timestamp(timestamp: Any) -> str:
    """Render an ISO string or datetime as ``YYYY-MM-DD HH:MM``."""
    if not timestamp:
        return "Unknown date"
    if isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M")
    try:
        return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).strftime(
            "%Y-%m-%d %H:%M"
        )
    except ValueError:
        return str(timestamp)


def format_similar_setups_for_template(
    similar_setups: List[Any],
    rag_metrics: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Format similar setups as a one-sentence precedent for template-based
    reasoning (no LLM).

    Uses AlgoRAG's own ``rag_metrics`` aggregate when it is present and
    non-empty (``sample_size > 0``) -- the same numbers the Confluence Scorer
    consumes, so the reasoning and the score never disagree. Otherwise the
    aggregate is derived from *similar_setups* directly: win rate over all
    setups, average R over the setups whose R-multiple is known (a missing
    R-multiple is not counted as 0R).

    Args:
        similar_setups: Similar setups from AlgoRAG (flat or nested shape,
            see :func:`normalize_similar_setup`).
        rag_metrics: Optional AlgoRAG ``rag_metrics`` dict.

    Returns:
        ``"Historical precedent: N similar setups with X% win rate and Y.YR
        average outcome."``, or ``""`` when there are no similar setups.
    """
    if not similar_setups:
        return ""

    metrics = rag_metrics or {}
    sample_size = metrics.get("sample_size")
    win_rate = to_float(metrics.get("win_rate_similar"))
    avg_r = to_float(metrics.get("avg_r_multiple_similar"))

    if not (isinstance(sample_size, int) and sample_size > 0 and win_rate is not None and avg_r is not None):
        fields = [normalize_similar_setup(s) for s in similar_setups]
        sample_size = len(fields)
        wins = sum(1 for f in fields if f.get("outcome_result") == "WIN")
        win_rate = wins / sample_size
        r_values = [r for r in (to_float(f.get("outcome_r_multiple")) for f in fields) if r is not None]
        avg_r = sum(r_values) / len(r_values) if r_values else None

    avg_text = f"{avg_r:.1f}R average outcome" if avg_r is not None else "an unknown average outcome"
    return (
        f"Historical precedent: {sample_size} similar setups with {win_rate:.0%} win rate "
        f"and {avg_text}."
    )
