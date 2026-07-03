"""
Re-ranking algorithm for AlgoRAG retrieval results.

Combines outcome quality + recency + confluence overlap to produce final scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import List

from services.algorag.models import SimilarSetup


@dataclass
class ReRankingConfig:
    """Configuration for re-ranking weights and parameters."""
    
    outcome_weight: float = 0.5     # Weight for outcome quality (R-multiple)
    recency_weight: float = 0.3     # Weight for recency score
    confluence_weight: float = 0.2  # Weight for confluence overlap
    
    recency_half_life_days: float = 90.0  # 90-day half-life for exponential decay
    max_r_multiple: float = 10.0    # Max R-multiple for normalization (clamp above this)


def compute_recency_score(setup_timestamp: datetime, current_timestamp: datetime) -> float:
    """Compute recency score using exponential decay with 90-day half-life.
    
    Args:
        setup_timestamp: When the historical setup occurred
        current_timestamp: Current time reference
        
    Returns:
        Float in [0.0, 1.0] where 1.0 = most recent, 0.5 = 90 days ago
    """
    days_ago = (current_timestamp - setup_timestamp).total_seconds() / (24 * 3600)
    days_ago = max(0.0, days_ago)  # Ensure non-negative
    
    # Exponential decay: score = 0.5^(days_ago / half_life)
    half_life = 90.0
    score = math.pow(0.5, days_ago / half_life)
    return min(1.0, score)  # Clamp to [0, 1]


def compute_outcome_score(r_multiple: float, max_r_multiple: float = 10.0) -> float:
    """Compute outcome quality score from R-multiple.
    
    Args:
        r_multiple: The R-multiple achieved by the setup
        max_r_multiple: Maximum R-multiple for normalization
        
    Returns:
        Float in [0.0, 1.0] where 1.0 = excellent outcome
    """
    if r_multiple <= 0.0:
        return 0.0
    
    # Normalize R-multiple to [0, 1] range, clamping above max_r_multiple
    normalized = min(r_multiple, max_r_multiple) / max_r_multiple
    return normalized


def compute_confluence_score(setup_confluence_count: int, current_confluence_count: int) -> float:
    """Compute confluence overlap score.
    
    Args:
        setup_confluence_count: Number of confluence factors in historical setup
        current_confluence_count: Number of confluence factors in current setup
        
    Returns:
        Float in [0.0, 1.0] representing similarity in confluence complexity
        1.0 = perfect match, 0.0 = no overlap
    """
    if setup_confluence_count == 0 and current_confluence_count == 0:
        return 1.0  # Both have no confluence - perfect match
    
    if setup_confluence_count == 0 or current_confluence_count == 0:
        return 0.0  # One has confluence, other doesn't - no overlap
    
    # Jaccard-like similarity: min / max
    min_count = min(setup_confluence_count, current_confluence_count)
    max_count = max(setup_confluence_count, current_confluence_count)
    
    return min_count / max_count


def compute_final_score(
    outcome_r_multiple: float,
    setup_timestamp: datetime,
    current_timestamp: datetime,
    setup_confluence_count: int,
    current_confluence_count: int,
    config: ReRankingConfig | None = None,
) -> float:
    """Compute final re-ranking score from all components.
    
    Args:
        outcome_r_multiple: R-multiple of the historical setup
        setup_timestamp: When the setup occurred
        current_timestamp: Current time reference
        setup_confluence_count: Confluence count of historical setup
        current_confluence_count: Confluence count of current setup
        config: Re-ranking configuration (uses default if None)
        
    Returns:
        Final score in [0.0, 1.0]
    """
    if config is None:
        config = ReRankingConfig()
    
    # Compute individual component scores
    outcome_score = compute_outcome_score(outcome_r_multiple, config.max_r_multiple)
    recency_score = compute_recency_score(setup_timestamp, current_timestamp)
    confluence_score = compute_confluence_score(setup_confluence_count, current_confluence_count)
    
    # Weighted combination
    final_score = (
        config.outcome_weight * outcome_score +
        config.recency_weight * recency_score +
        config.confluence_weight * confluence_score
    )
    
    return min(1.0, max(0.0, final_score))  # Clamp to [0, 1]


def rerank_setups(
    setups: List[SimilarSetup],
    current_confluence_count: int,
    current_timestamp: datetime | None = None,
    config: ReRankingConfig | None = None,
) -> List[SimilarSetup]:
    """Re-rank a list of similar setups using the composite scoring algorithm.
    
    Args:
        setups: List of similar setups with similarity scores
        current_confluence_count: Number of confluence factors in current setup
        current_timestamp: Current time reference (uses now if None)
        config: Re-ranking configuration
        
    Returns:
        New list of setups sorted by final_score (descending)
    """
    if not setups:
        return []
    
    if current_timestamp is None:
        current_timestamp = datetime.now(setups[0].timestamp.tzinfo)
    
    if config is None:
        config = ReRankingConfig()
    
    # Create new list with updated final_score
    reranked = []
    for setup in setups:
        # Compute final score
        final_score = compute_final_score(
            outcome_r_multiple=setup.outcome_r_multiple,
            setup_timestamp=setup.timestamp,
            current_timestamp=current_timestamp,
            setup_confluence_count=setup.confluence_count,
            current_confluence_count=current_confluence_count,
            config=config,
        )
        
        # Create new setup with updated final_score
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
            similarity_score=setup.similarity_score,  # Keep original similarity
            final_score=final_score,  # Updated with re-ranking
            full_setup=setup.full_setup,
        )
        reranked.append(reranked_setup)
    
    # Sort by final_score descending
    reranked.sort(key=lambda s: s.final_score, reverse=True)
    
    return reranked