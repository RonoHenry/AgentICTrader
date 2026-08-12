"""
Re-ranking algorithm for AlgoRAG similar setups.

Implements Task 10.4: Re-rank retrieved setups by outcome quality + recency + confluence overlap.
Uses exponential decay for recency (90-day half-life) and configurable weights.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from services.algorag.models import SimilarSetup


@dataclass
class ReRankingConfig:
    """Configuration for re-ranking algorithm."""
    outcome_weight: float = 0.5
    recency_weight: float = 0.3
    confluence_weight: float = 0.2
    recency_half_life_days: float = 90.0
    max_r_multiple: float = 10.0


def compute_recency_score(setup_timestamp: datetime, current_timestamp: datetime, half_life_days: float = 90.0) -> float:
    """
    Compute recency score using exponential decay.
    
    Args:
        setup_timestamp: When the setup occurred
        current_timestamp: Current time for comparison
        half_life_days: Days for score to decay to 0.5 (default 90)
        
    Returns:
        Score between 0.0 and 1.0, where 1.0 is current time
    """
    # Calculate days ago (negative if future)
    days_ago = (current_timestamp - setup_timestamp).total_seconds() / (24 * 3600)
    
    # Clamp future times to score of 1.0
    if days_ago <= 0:
        return 1.0
    
    # Exponential decay: score = 0.5^(days_ago / half_life)
    score = 0.5 ** (days_ago / half_life_days)
    
    return max(0.0, min(1.0, score))


def compute_outcome_score(outcome_r_multiple: float, max_r_multiple: float = 10.0) -> float:
    """
    Compute outcome quality score normalized by maximum R-multiple.
    
    Args:
        outcome_r_multiple: The R-multiple achieved (can be negative)
        max_r_multiple: Maximum R-multiple for normalization
        
    Returns:
        Score between 0.0 and 1.0, where 1.0 is max_r_multiple
    """
    # Negative R-multiples get 0 score
    if outcome_r_multiple <= 0:
        return 0.0
    
    # Normalize by max and clamp to [0, 1]
    score = outcome_r_multiple / max_r_multiple
    
    return max(0.0, min(1.0, score))


def compute_confluence_score(setup_confluence_count: int, current_confluence_count: int) -> float:
    """
    Compute confluence overlap score using Jaccard-like similarity.
    
    Args:
        setup_confluence_count: Number of confluence factors in historical setup
        current_confluence_count: Number of confluence factors in current setup
        
    Returns:
        Score between 0.0 and 1.0, where 1.0 is perfect match
    """
    # If both have zero confluence, perfect match
    if setup_confluence_count == 0 and current_confluence_count == 0:
        return 1.0
    
    # If one has zero but other doesn't, no overlap
    if setup_confluence_count == 0 or current_confluence_count == 0:
        return 0.0
    
    # Jaccard similarity: min/max
    min_count = min(setup_confluence_count, current_confluence_count)
    max_count = max(setup_confluence_count, current_confluence_count)
    
    return min_count / max_count


def compute_final_score(
    outcome_r_multiple: float,
    setup_timestamp: datetime,
    current_timestamp: datetime,
    setup_confluence_count: int,
    current_confluence_count: int,
    config: ReRankingConfig,
) -> float:
    """
    Compute final weighted score combining outcome, recency, and confluence.
    
    Args:
        outcome_r_multiple: R-multiple of the setup
        setup_timestamp: When setup occurred
        current_timestamp: Current time
        setup_confluence_count: Confluence factors in setup
        current_confluence_count: Confluence factors in current situation
        config: Re-ranking configuration with weights
        
    Returns:
        Final score between 0.0 and 1.0
    """
    outcome_score = compute_outcome_score(outcome_r_multiple, config.max_r_multiple)
    recency_score = compute_recency_score(setup_timestamp, current_timestamp, config.recency_half_life_days)
    confluence_score = compute_confluence_score(setup_confluence_count, current_confluence_count)
    
    final_score = (
        config.outcome_weight * outcome_score +
        config.recency_weight * recency_score +
        config.confluence_weight * confluence_score
    )
    
    return max(0.0, min(1.0, final_score))


def rerank_setups(
    setups: List[SimilarSetup],
    current_confluence_count: int,
    current_timestamp: Optional[datetime] = None,
    config: Optional[ReRankingConfig] = None,
) -> List[SimilarSetup]:
    """
    Re-rank setups by outcome quality + recency + confluence overlap.
    
    Args:
        setups: List of similar setups from vector search
        current_confluence_count: Number of confluence factors in current setup
        current_timestamp: Current time (defaults to now)
        config: Re-ranking configuration (defaults to standard config)
        
    Returns:
        List of setups sorted by final_score descending
    """
    if not setups:
        return []
    
    if current_timestamp is None:
        current_timestamp = datetime.now(timezone.utc)
    
    if config is None:
        config = ReRankingConfig()
    
    # Compute final scores for all setups
    reranked_setups = []
    for setup in setups:
        # Create copy to avoid modifying original
        reranked_setup = SimilarSetup(
            trade_id=setup.trade_id,
            timestamp=setup.timestamp,
            instrument=setup.instrument,
            time_window=setup.time_window,
            htf_open_bias=setup.htf_open_bias,
            confluence_count=setup.confluence_count,
            outcome_result=setup.outcome_result,
            outcome_r_multiple=setup.outcome_r_multiple,
            narrative=setup.narrative,
            similarity_score=setup.similarity_score,  # Preserve original
            final_score=compute_final_score(
                outcome_r_multiple=setup.outcome_r_multiple,
                setup_timestamp=setup.timestamp,
                current_timestamp=current_timestamp,
                setup_confluence_count=setup.confluence_count,
                current_confluence_count=current_confluence_count,
                config=config,
            ),
            full_setup=setup.full_setup,
        )
        reranked_setups.append(reranked_setup)
    
    # Sort by final score descending
    return sorted(reranked_setups, key=lambda s: s.final_score, reverse=True)
