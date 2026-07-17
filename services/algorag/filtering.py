"""
Metadata filtering utilities for AlgoRAG retrieval endpoint.

Builds Qdrant filter objects from RetrievalRequest parameters to enable
fast metadata pre-filtering before vector similarity search.
"""

from __future__ import annotations

from qdrant_client.http import models as qmodels

from services.algorag.models import RetrievalRequest


def build_qdrant_filter(request: RetrievalRequest) -> qmodels.Filter:
    """
    Build a Qdrant Filter object from RetrievalRequest parameters.
    
    Creates FieldCondition objects for each non-empty filter parameter:
    - instrument (required): Always included
    - time_window (optional): Included if not None or empty string
    - htf_open_bias (optional): Included if not None or empty string  
    - outcome_filter (optional): Included if not None or empty string
    
    Args:
        request: The retrieval request containing filter parameters
        
    Returns:
        Qdrant Filter object with must conditions for metadata filtering
        
    Requirements: FR-RAG-2 (metadata filtering for retrieval)
    """
    must_conditions = []
    
    # Instrument is required - always add this condition
    must_conditions.append(
        qmodels.FieldCondition(
            key="instrument",
            match=qmodels.MatchValue(value=request.instrument),
        )
    )
    
    # Add optional filters if they have non-empty values
    if request.time_window and request.time_window.strip():
        must_conditions.append(
            qmodels.FieldCondition(
                key="time_window", 
                match=qmodels.MatchValue(value=request.time_window),
            )
        )
        
    if request.htf_open_bias and request.htf_open_bias.strip():
        must_conditions.append(
            qmodels.FieldCondition(
                key="htf_open_bias",
                match=qmodels.MatchValue(value=request.htf_open_bias),
            )
        )
        
    if request.outcome_filter and request.outcome_filter.strip():
        must_conditions.append(
            qmodels.FieldCondition(
                key="outcome_result",
                match=qmodels.MatchValue(value=request.outcome_filter),
            )
        )
    
    return qmodels.Filter(must=must_conditions)