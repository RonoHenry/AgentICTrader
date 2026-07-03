"""
Diversity filtering for AlgoRAG retrieval results.

Limits the number of setups from the same calendar day to ensure temporal diversity.
"""

from __future__ import annotations

from collections import defaultdict
from typing import List

from services.algorag.models import SimilarSetup


def apply_diversity_filter(
    setups: List[SimilarSetup],
    max_per_day: int = 3,
) -> List[SimilarSetup]:
    """Apply diversity filtering to limit setups from the same calendar day.
    
    Args:
        setups: List of setups (should already be sorted by final_score descending)
        max_per_day: Maximum number of setups allowed from the same calendar day
        
    Returns:
        Filtered list maintaining original order but with diversity constraints applied
    """
    if not setups:
        return []
    
    if max_per_day <= 0:
        return []
    
    # Track how many setups we've included from each calendar day
    daily_counts: dict[str, int] = defaultdict(int)
    filtered: List[SimilarSetup] = []
    
    for setup in setups:
        # Extract calendar date as string (YYYY-MM-DD)
        date_key = setup.timestamp.date().isoformat()
        
        # Check if we can include this setup (haven't exceeded daily limit)
        if daily_counts[date_key] < max_per_day:
            filtered.append(setup)
            daily_counts[date_key] += 1
    
    return filtered