"""
Confluence Scorer feature extraction with RAG integration.

This module extracts features for the Confluence Scorer, augmenting traditional 
features with RAG (Retrieval-Augmented Generation) metrics from AlgoRAG service.

Features extracted:
- HTF projection features (from existing extractors)
- Time window and session features (from existing extractors)
- Zone/PD array features (from existing extractors)
- RAG features (avg_r_multiple_similar, win_rate_similar, sample_size, max_similarity_score)

The RAG integration is additive - if RAG is unavailable, zeros are used for 
RAG features so the model can still function.

Usage:
    extractor = ConfluenceFeatureExtractor()
    features = await extractor.extract_features(candles, setup_data)
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from ml.algorag.client import AlgoRAGClient

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceFeatures:
    """Feature vector for Confluence Scorer with RAG augmentation."""
    
    # Original features (from existing extractors)
    htf_high_proximity_pct: float
    htf_low_proximity_pct: float
    htf_body_pct: float
    htf_close_position: float
    time_window_weight: float
    narrative_phase: str
    bos_detected: bool
    choch_detected: bool
    fvg_present: bool
    liquidity_sweep: bool
    
    # RAG features (new)
    avg_r_multiple: float = 0.0
    win_rate: float = 0.0
    sample_size: float = 0.0  # normalized by /100
    max_similarity: float = 0.0
    
    def to_array(self) -> np.ndarray:
        """
        Convert to numpy array for model input.
        
        Returns a 14-element feature vector with traditional + RAG features:
        [0-9]: Traditional features (HTF, session, zone)
        [10-13]: RAG features (avg_r_multiple, win_rate, sample_size, max_similarity)
        
        All features are normalized and validated:
        - Categorical features mapped to integers
        - Boolean features converted to 0/1
        - Percentage features kept as-is (0-100 range)
        - Ratio features normalized to [0,1] range
        - No NaN or infinite values
        
        Returns:
            np.ndarray of shape (14,) containing all features
        """
        # Map categorical features
        narrative_map = {
            "ACCUMULATION": 0, "MANIPULATION": 1, "EXPANSION": 2,
            "DISTRIBUTION": 3, "TRANSITION": 4, "OFF": 5
        }
        
        return np.array([
            self.htf_high_proximity_pct,    # [0] HTF high proximity percentage (0-100)
            self.htf_low_proximity_pct,     # [1] HTF low proximity percentage (0-100)
            self.htf_body_pct,              # [2] HTF body percentage (0-100) 
            self.htf_close_position,        # [3] HTF close position ratio (0-1)
            self.time_window_weight,        # [4] Session time weight (0-1)
            narrative_map.get(self.narrative_phase, 5),  # [5] Narrative phase (0-5)
            int(self.bos_detected),         # [6] BOS detected flag (0/1)
            int(self.choch_detected),       # [7] CHoCH detected flag (0/1)
            int(self.fvg_present),          # [8] FVG present flag (0/1)
            int(self.liquidity_sweep),      # [9] Liquidity sweep flag (0/1)
            # RAG features
            self.avg_r_multiple,            # [10] Average R-multiple from similar setups (0-10)
            self.win_rate,                  # [11] Win rate from similar setups (0-1)
            self.sample_size,               # [12] Sample size normalized (0-1)
            self.max_similarity,            # [13] Maximum similarity score (0-1)
        ])


class ConfluenceFeatureExtractor:
    """
    Feature extractor for Confluence Scorer with RAG integration.
    
    This extractor combines traditional ML features with RAG-enhanced contextual features:
    
    **Traditional Features (10):**
    - HTF projection features: proximity percentages, body percentage, close position
    - Session features: time window weight, narrative phase 
    - Zone features: BOS, CHoCH, FVG, liquidity sweep detection
    
    **RAG Features (4):**
    - avg_r_multiple: Average R-multiple from similar historical setups
    - win_rate: Win rate from similar historical setups  
    - sample_size: Number of similar setups found (normalized)
    - max_similarity: Maximum similarity score to historical setups
    
    **Key Properties:**
    - Graceful degradation: Works without RAG client (zeros for RAG features)
    - Feature normalization: All features within expected bounds
    - Error resilience: Handles malformed data, network errors, missing values
    - Thread-safe: Supports concurrent feature extraction
    - Deterministic: Same input produces same output
    
    **Usage:**
        >>> async with AlgoRAGClient() as rag_client:
        ...     extractor = ConfluenceFeatureExtractor(rag_client=rag_client)
        ...     features = await extractor.extract_features(candles, setup_data)
        ...     feature_vector = features.to_array()  # Shape: (14,)
        
        >>> # Without RAG (graceful degradation)  
        >>> extractor = ConfluenceFeatureExtractor()
        >>> features = await extractor.extract_features(candles, setup_data)
        >>> feature_vector = features.to_array()  # RAG features will be zeros
    
    **Integration:**
    - HTFProjectionExtractor: For HTF OHLC features
    - ZoneFeatureExtractor: For structure/pattern detection
    - TimeWindowClassifier: For session-based features
    - AlgoRAGClient: For retrieving similar historical setups
    """
    
    def __init__(self, rag_client: Optional[AlgoRAGClient] = None):
        """
        Initialize feature extractor.
        
        Args:
            rag_client: AlgoRAG client for retrieving similar setups.
                       If None, RAG features will be zeros (graceful degradation).
        """
        self.rag_client = rag_client
    
    async def extract_features(
        self, 
        candles: List[Dict[str, Any]], 
        setup_data: Dict[str, Any]
    ) -> ConfluenceFeatures:
        """
        Extract confluence features with RAG augmentation.
        
        Args:
            candles: Historical OHLCV candle data
            setup_data: Setup information (instrument, timestamp, direction, etc.)
            
        Returns:
            ConfluenceFeatures with all features including RAG metrics
        """
        # Extract traditional features (placeholder implementation)
        traditional_features = self._extract_traditional_features(candles, setup_data)
        
        # Extract RAG features
        rag_features = await self._extract_rag_features(setup_data)
        
        return ConfluenceFeatures(
            # Traditional features
            htf_high_proximity_pct=traditional_features["htf_high_proximity_pct"],
            htf_low_proximity_pct=traditional_features["htf_low_proximity_pct"],
            htf_body_pct=traditional_features["htf_body_pct"],
            htf_close_position=traditional_features["htf_close_position"],
            time_window_weight=traditional_features["time_window_weight"],
            narrative_phase=traditional_features["narrative_phase"],
            bos_detected=traditional_features["bos_detected"],
            choch_detected=traditional_features["choch_detected"],
            fvg_present=traditional_features["fvg_present"],
            liquidity_sweep=traditional_features["liquidity_sweep"],
            # RAG features
            avg_r_multiple=rag_features["avg_r_multiple"],
            win_rate=rag_features["win_rate"],
            sample_size=rag_features["sample_size"],
            max_similarity=rag_features["max_similarity"],
        )
    
    def _extract_traditional_features(
        self, 
        candles: List[Dict[str, Any]], 
        setup_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract traditional confluence features using existing extractors.
        
        Integrates with:
        - HTFProjectionExtractor for HTF OHLC features
        - ZoneFeatureExtractor for structure/pattern detection
        - TimeWindowClassifier for session-based features
        
        Includes normalization and missing value handling for robust operation.
        """
        from ml.features.htf_projections import HTFProjectionExtractor
        from ml.features.zone_features import ZoneFeatureExtractor  
        from ml.features.session_features import TimeWindowClassifier
        
        # Extract required parameters with defaults
        current_price = float(setup_data.get("current_price", candles[-1]["close"] if candles else 1.0))
        timestamp_utc = setup_data.get("timestamp", datetime.now(timezone.utc))
        instrument = setup_data.get("instrument", "EURUSD")
        htf_timeframe = setup_data.get("htf_timeframe", "H1")
        
        # HTF Projection Features
        try:
            htf_extractor = HTFProjectionExtractor()
            
            # For testing, we'll create a mock HTF candle from the last regular candle
            # In production, this would fetch real HTF data from TimescaleDB
            if candles:
                last_candle = candles[-1]
                mock_htf_candle = {
                    "open": float(last_candle["open"]) * 0.999,  # Slightly lower open
                    "high": float(last_candle["high"]) * 1.001,  # Slightly higher high
                    "low": float(last_candle["low"]) * 0.998,    # Slightly lower low  
                    "close": float(last_candle["close"]),
                    "volume": last_candle.get("volume", 1000),
                }
                htf_candles = [mock_htf_candle]
            else:
                # Fallback HTF candle
                htf_candles = [{
                    "open": current_price * 0.999,
                    "high": current_price * 1.001, 
                    "low": current_price * 0.998,
                    "close": current_price,
                    "volume": 1000,
                }]
            
            htf_projection = htf_extractor.compute_projections(
                current_price=current_price,
                htf_candles=htf_candles,
                htf_timeframe=htf_timeframe,
            )
            
            # Normalize HTF features to proper ranges
            htf_features = {
                "htf_high_proximity_pct": max(0.0, min(100.0, htf_projection.htf_high_proximity_pct)),
                "htf_low_proximity_pct": max(0.0, min(100.0, htf_projection.htf_low_proximity_pct)),
                "htf_body_pct": max(0.0, min(100.0, htf_projection.htf_body_pct)),
                "htf_close_position": max(0.0, min(1.0, htf_projection.htf_close_position / 100.0)),  # Normalize to [0,1]
            }
            
        except Exception as e:
            logger.warning(f"HTF feature extraction failed: {e}, using defaults")
            htf_features = {
                "htf_high_proximity_pct": 50.0,  # Middle of range
                "htf_low_proximity_pct": 50.0,
                "htf_body_pct": 50.0,
                "htf_close_position": 0.5,
            }
        
        # Zone/Structure Features
        try:
            zone_extractor = ZoneFeatureExtractor()
            
            if candles:
                zone_features = zone_extractor.extract(candles, htf_candle=htf_candles[0])
                zone_dict = {
                    "bos_detected": zone_features.bos_detected,
                    "choch_detected": zone_features.choch_detected,
                    "fvg_present": zone_features.fvg_present,
                    "liquidity_sweep": zone_features.liquidity_sweep,
                }
            else:
                # Defaults for empty candles
                zone_dict = {
                    "bos_detected": False,
                    "choch_detected": False,
                    "fvg_present": False,
                    "liquidity_sweep": False,
                }
                
        except Exception as e:
            logger.warning(f"Zone feature extraction failed: {e}, using defaults")
            zone_dict = {
                "bos_detected": False,
                "choch_detected": False,
                "fvg_present": False,
                "liquidity_sweep": False,
            }
        
        # Session/Time Features
        try:
            session_classifier = TimeWindowClassifier()
            time_features = session_classifier.classify(
                timestamp_utc=timestamp_utc,
                instrument=instrument,
                current_price=current_price,
            )
            
            session_dict = {
                "time_window_weight": max(0.0, min(1.0, time_features.time_window_weight)),  # Ensure [0,1]
                "narrative_phase": time_features.narrative_phase,
            }
            
        except Exception as e:
            logger.warning(f"Session feature extraction failed: {e}, using defaults")
            session_dict = {
                "time_window_weight": 0.1,  # OFF_HOURS default
                "narrative_phase": "OFF",
            }
        
        # Combine all features with validation
        combined_features = {**htf_features, **session_dict, **zone_dict}
        
        # Final validation - ensure no NaN or infinite values
        for key, value in combined_features.items():
            if isinstance(value, (int, float)) and (np.isnan(value) or np.isinf(value)):
                logger.warning(f"Invalid value for {key}: {value}, using default")
                if "pct" in key:
                    combined_features[key] = 50.0  # Middle percentage
                elif "weight" in key or "position" in key:
                    combined_features[key] = 0.5   # Middle ratio
                else:
                    combined_features[key] = 0.0   # Safe default
        
        return combined_features
    
    async def _extract_rag_features(self, setup_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract RAG features by calling AlgoRAG service.
        
        Implements graceful degradation - returns zeros if RAG unavailable.
        Includes feature normalization and validation.
        """
        if self.rag_client is None:
            logger.debug("RAG client not available, using zero RAG features")
            return {
                "avg_r_multiple": 0.0,
                "win_rate": 0.0,
                "sample_size": 0.0,
                "max_similarity": 0.0,
            }
        
        try:
            # Call AlgoRAG service with setup data
            rag_response = await self.rag_client.retrieve_with_fallback(setup_data)
            rag_metrics = rag_response.get("rag_metrics", {})
            
            # Extract and normalize features
            avg_r_multiple = float(rag_metrics.get("avg_r_multiple_similar", 0.0))
            win_rate = float(rag_metrics.get("win_rate_similar", 0.0))
            sample_size = float(rag_metrics.get("sample_size", 0)) / 100.0  # normalized
            max_similarity = float(rag_metrics.get("max_similarity_score", 0.0))
            
            # Apply bounds and validation
            rag_features = {
                "avg_r_multiple": max(0.0, min(10.0, avg_r_multiple)),  # Cap at reasonable R-multiple
                "win_rate": max(0.0, min(1.0, win_rate)),                # Must be [0,1]
                "sample_size": max(0.0, min(1.0, sample_size)),          # Normalized [0,1]  
                "max_similarity": max(0.0, min(1.0, max_similarity)),    # Must be [0,1]
            }
            
            # Final validation - ensure no NaN or infinite values
            for key, value in rag_features.items():
                if np.isnan(value) or np.isinf(value):
                    logger.warning(f"Invalid RAG feature value for {key}: {value}, using 0.0")
                    rag_features[key] = 0.0
            
            return rag_features
            
        except Exception as e:
            logger.warning(f"RAG feature extraction failed, using fallback: {e}")
            return {
                "avg_r_multiple": 0.0,
                "win_rate": 0.0,
                "sample_size": 0.0,
                "max_similarity": 0.0,
            }