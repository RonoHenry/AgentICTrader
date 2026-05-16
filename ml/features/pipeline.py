"""
Feature pipeline orchestration.

This module composes HTFProjectionExtractor + CandleFeatureExtractor +
ZoneFeatureExtractor + SessionFeatureExtractor into a single sklearn-compatible
Pipeline that outputs a flat feature vector as a pandas DataFrame.

The pipeline includes Great Expectations data quality validations to ensure:
- No nulls in HTF projection columns
- All percentage values are in [0, 100] range
- Enum values (open_bias, htf_trend_bias) are in valid sets

New features added in Task 28 (sentiment integration):
- ``sentiment_score`` (float, -1.0 to +1.0): per-instrument directional sentiment
  score sourced from Redis key ``sentiment:{instrument}`` (TTL 900s).
- ``blackout_active`` (bool): whether a HIGH-impact economic event is within ±15 min,
  sourced from Redis key ``blackout:{instrument}`` (TTL 120s).

**Implements: Task 14 - Build sklearn feature pipeline orchestration**
**Updated: Task 28 - Integrate sentiment into Confluence Scorer and retrain**

Example usage:
    >>> from ml.features.pipeline import FeaturePipeline
    >>> pipeline = FeaturePipeline()
    >>> candles = [
    ...     {"time": "2024-01-01T00:00:00Z", "open": 1.5000, "high": 1.5100, "low": 1.4950, "close": 1.5080, "volume": 1000},
    ...     {"time": "2024-01-01T00:05:00Z", "open": 1.5080, "high": 1.5090, "low": 1.5020, "close": 1.5030, "volume": 1200},
    ...     {"time": "2024-01-01T00:10:00Z", "open": 1.5030, "high": 1.5150, "low": 1.5020, "close": 1.5140, "volume": 1500},
    ... ]
    >>> htf_candle = {"time": "2024-01-01T00:00:00Z", "open": 1.5000, "high": 1.5200, "low": 1.4900, "close": 1.5180, "volume": 5000}
    >>> features_df = pipeline.transform(candles=candles, htf_candle=htf_candle, instrument="EURUSD")
    >>> features_df.shape
    (1, 30)  # 1 row, 30+ feature columns
    
    >>> # Validate data quality
    >>> pipeline.validate_data_quality(features_df)
    True
"""

import pandas as pd
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from ml.features.htf_projections import HTFProjectionExtractor
from ml.features.candle_features import CandleFeatureExtractor
from ml.features.zone_features import ZoneFeatureExtractor
from ml.features.session_features import TimeWindowClassifier


class DataQualityError(Exception):
    """Exception raised when data quality validation fails."""
    pass


class FeaturePipeline:
    """
    Feature pipeline orchestration.
    
    Composes all feature extractors into a single pipeline that produces
    a flat feature vector as a pandas DataFrame with named columns.
    
    This pipeline is stateless (no fit required) and can be used directly
    for both training and inference.
    
    The pipeline includes Great Expectations-style data quality validations:
    - No nulls in HTF projection columns
    - All percentage values in [0, 100] range (except proximity which can exceed)
    - Enum values (open_bias, htf_trend_bias) in valid sets
    
    **Implements: Task 14 - Build sklearn feature pipeline orchestration**
    
    Attributes:
        htf_extractor: HTF projection feature extractor
        candle_extractor: Candle structure feature extractor
        zone_extractor: Zone and structure feature extractor
        session_classifier: Session and time feature classifier
        enable_validation: Whether to run data quality validation (default: True)
    """
    
    # Data quality validation constants
    VALID_BIAS_VALUES = {"BULLISH", "BEARISH", "NEUTRAL"}
    HTF_PROJECTION_COLUMNS = [
        "htf_open",
        "htf_high",
        "htf_low",
        "htf_open_bias",
        "htf_high_proximity_pct",
        "htf_low_proximity_pct",
        "htf_body_pct",
        "htf_upper_wick_pct",
        "htf_lower_wick_pct",
        "htf_close_position",
    ]
    PERCENTAGE_COLUMNS = [
        "htf_body_pct",
        "htf_upper_wick_pct",
        "htf_lower_wick_pct",
        "body_pct",
        "upper_wick_pct",
        "lower_wick_pct",
    ]
    
    def __init__(self, enable_validation: bool = True):
        """
        Initialize the feature pipeline with all extractors.
        
        Args:
            enable_validation: Whether to run data quality validation after transform
                              (default: True). Set to False for performance-critical paths.
        """
        self.htf_extractor = HTFProjectionExtractor()
        self.candle_extractor = CandleFeatureExtractor()
        self.zone_extractor = ZoneFeatureExtractor()
        self.session_classifier = TimeWindowClassifier()
        self.enable_validation = enable_validation
    
    def fit(self, **kwargs):
        """
        Fit the pipeline (no-op for stateless pipeline).
        
        This method exists for sklearn compatibility but does nothing
        since all extractors are stateless.
        
        Args:
            **kwargs: Ignored
            
        Returns:
            self for method chaining
        """
        return self
    
    def transform(
        self,
        candles: List[Dict[str, Any]],
        htf_candle: Dict[str, Any],
        instrument: str,
        htf_timeframe: Optional[str] = None,
        daily_open: Optional[float] = None,
        weekly_open: Optional[float] = None,
        true_day_open: Optional[float] = None,
        sentiment_score: float = 0.0,
        blackout_active: bool = False,
    ) -> pd.DataFrame:
        """
        Transform candle data into a flat feature vector.
        
        Args:
            candles: List of candle dictionaries with OHLCV data (chronological order)
            htf_candle: HTF candle dictionary with OHLCV data
            instrument: Trading instrument (e.g., "EURUSD", "US500")
            htf_timeframe: HTF timeframe identifier (e.g., "H1", "H4", "D1")
                          If None, defaults to "H1"
            daily_open: Daily open price at 18:00 NY (optional)
            weekly_open: Weekly open price at Sunday 18:00 NY (optional)
            true_day_open: True day open price at 00:00 NY (optional)
            sentiment_score: Per-instrument directional sentiment score in [-1.0, +1.0].
                            Sourced from Redis key ``sentiment:{instrument}`` (TTL 900s).
                            Defaults to 0.0 (neutral) when not provided.
            blackout_active: Whether a HIGH-impact economic event is within ±15 min.
                            Sourced from Redis key ``blackout:{instrument}`` (TTL 120s).
                            Defaults to False when not provided.
            
        Returns:
            pandas DataFrame with one row and named feature columns
            
        Raises:
            ValueError: If candles or htf_candle is invalid
        """
        if not candles:
            raise ValueError("candles list cannot be empty")
        
        if not htf_candle:
            raise ValueError("htf_candle cannot be None")
        
        # Default HTF timeframe
        if htf_timeframe is None:
            htf_timeframe = "H1"
        
        # Get the most recent candle for current price and timestamp
        current_candle = candles[-1]
        current_price = float(current_candle["close"])
        
        # Parse timestamp (handle both string and datetime)
        if isinstance(current_candle["time"], str):
            timestamp_utc = datetime.fromisoformat(
                current_candle["time"].replace("Z", "+00:00")
            )
        else:
            timestamp_utc = current_candle["time"]
        
        # Ensure timezone-aware
        if timestamp_utc.tzinfo is None:
            timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
        
        # Extract HTF projection features
        htf_projection = self.htf_extractor.compute_projections(
            current_price=current_price,
            htf_candles=[htf_candle],
            htf_timeframe=htf_timeframe,
        )
        
        # Extract candle structure features
        candle_features = self.candle_extractor.extract(current_candle)
        
        # Extract zone and structure features
        zone_features = self.zone_extractor.extract(
            candles=candles,
            htf_candle=htf_candle,
        )
        
        # Extract session and time features
        session_features = self.session_classifier.classify(
            timestamp_utc=timestamp_utc,
            instrument=instrument,
            current_price=current_price,
            daily_open=daily_open,
            weekly_open=weekly_open,
            true_day_open=true_day_open,
        )
        
        # Combine all features into a flat dictionary
        feature_dict = {}
        
        # Add HTF projection features
        feature_dict.update(asdict(htf_projection))
        
        # Add candle structure features
        feature_dict.update(asdict(candle_features))
        
        # Add zone and structure features
        feature_dict.update(asdict(zone_features))
        
        # Add session and time features
        feature_dict.update(asdict(session_features))
        
        # Add sentiment and blackout features (Task 28)
        feature_dict["sentiment_score"] = float(sentiment_score)
        feature_dict["blackout_active"] = bool(blackout_active)
        
        # Convert to DataFrame (single row)
        df = pd.DataFrame([feature_dict])
        
        # Run data quality validation if enabled
        if self.enable_validation:
            self.validate_data_quality(df)
        
        return df
    
    def fit_transform(
        self,
        candles: List[Dict[str, Any]],
        htf_candle: Dict[str, Any],
        instrument: str,
        htf_timeframe: Optional[str] = None,
        daily_open: Optional[float] = None,
        weekly_open: Optional[float] = None,
        true_day_open: Optional[float] = None,
        sentiment_score: float = 0.0,
        blackout_active: bool = False,
    ) -> pd.DataFrame:
        """
        Fit and transform in one step (equivalent to transform for stateless pipeline).
        
        Args:
            candles: List of candle dictionaries with OHLCV data
            htf_candle: HTF candle dictionary with OHLCV data
            instrument: Trading instrument
            htf_timeframe: HTF timeframe identifier (optional)
            daily_open: Daily open price (optional)
            weekly_open: Weekly open price (optional)
            true_day_open: True day open price (optional)
            sentiment_score: Per-instrument directional sentiment score in [-1.0, +1.0].
                            Defaults to 0.0 (neutral) when not provided.
            blackout_active: Whether a HIGH-impact economic event is within ±15 min.
                            Defaults to False when not provided.
            
        Returns:
            pandas DataFrame with one row and named feature columns
        """
        # For stateless pipeline, fit_transform is equivalent to transform
        return self.transform(
            candles=candles,
            htf_candle=htf_candle,
            instrument=instrument,
            htf_timeframe=htf_timeframe,
            daily_open=daily_open,
            weekly_open=weekly_open,
            true_day_open=true_day_open,
            sentiment_score=sentiment_score,
            blackout_active=blackout_active,
        )
    
    def get_feature_names(self) -> List[str]:
        """
        Get the list of feature names produced by the pipeline.
        
        Returns:
            List of feature column names
            
        Note:
            This is a convenience method for inspecting the pipeline output.
            The actual feature names are determined dynamically during transform.
        """
        # Create a dummy transform to get feature names
        dummy_candles = [
            {
                "time": "2024-01-01T00:00:00Z",
                "open": 1.5000,
                "high": 1.5100,
                "low": 1.4950,
                "close": 1.5080,
                "volume": 1000,
            }
        ]
        dummy_htf_candle = {
            "time": "2024-01-01T00:00:00Z",
            "open": 1.5000,
            "high": 1.5200,
            "low": 1.4900,
            "close": 1.5180,
            "volume": 5000,
        }
        
        df = self.transform(
            candles=dummy_candles,
            htf_candle=dummy_htf_candle,
            instrument="EURUSD",
        )
        
        return list(df.columns)
    
    def validate_data_quality(self, df: pd.DataFrame) -> bool:
        """
        Validate data quality using Great Expectations-style checks.
        
        Validates:
        1. No nulls in HTF projection columns
        2. All percentage values in [0, 100] range
        3. Enum values (open_bias, htf_trend_bias) in valid sets
        4. Time window weight in [0.0, 1.0]
        5. Close position in [0.0, 1.0]
        
        Args:
            df: DataFrame to validate
            
        Returns:
            True if all validations pass
            
        Raises:
            DataQualityError: If any validation fails
        """
        # Validation 1: No nulls in HTF projection columns
        self._validate_no_nulls_in_htf_columns(df)
        
        # Validation 2: All percentage values in [0, 100] range
        self._validate_percentage_ranges(df)
        
        # Validation 3: Enum values in valid sets
        self._validate_enum_values(df)
        
        # Validation 4: Time window weight in [0.0, 1.0]
        self._validate_time_window_weight(df)
        
        # Validation 5: Close position in [0.0, 1.0]
        self._validate_close_position(df)
        
        return True
    
    def _validate_no_nulls_in_htf_columns(self, df: pd.DataFrame) -> None:
        """
        Validate no nulls in HTF projection columns.
        
        Args:
            df: DataFrame to validate
            
        Raises:
            DataQualityError: If nulls found in HTF columns
        """
        for col in self.HTF_PROJECTION_COLUMNS:
            if col in df.columns and df[col].isnull().any():
                raise DataQualityError(
                    f"Data quality validation failed: Null values found in HTF column '{col}'"
                )
    
    def _validate_percentage_ranges(self, df: pd.DataFrame) -> None:
        """
        Validate all percentage values are in [0, 100] range.
        
        Args:
            df: DataFrame to validate
            
        Raises:
            DataQualityError: If percentage values out of range
        """
        for col in self.PERCENTAGE_COLUMNS:
            if col in df.columns:
                min_val = df[col].min()
                max_val = df[col].max()
                
                # Allow small tolerance for floating point arithmetic
                if min_val < -0.01:
                    raise DataQualityError(
                        f"Data quality validation failed: {col} has values below 0 (min: {min_val})"
                    )
                if max_val > 100.01:
                    raise DataQualityError(
                        f"Data quality validation failed: {col} has values above 100 (max: {max_val})"
                    )
    
    def _validate_enum_values(self, df: pd.DataFrame) -> None:
        """
        Validate enum values are in valid sets.
        
        Args:
            df: DataFrame to validate
            
        Raises:
            DataQualityError: If enum values invalid
        """
        # Validate htf_open_bias
        if "htf_open_bias" in df.columns:
            invalid_values = df[~df["htf_open_bias"].isin(self.VALID_BIAS_VALUES)]["htf_open_bias"].unique()
            if len(invalid_values) > 0:
                raise DataQualityError(
                    f"Data quality validation failed: Invalid htf_open_bias values: {invalid_values}"
                )
        
        # Validate htf_trend_bias
        if "htf_trend_bias" in df.columns:
            invalid_values = df[~df["htf_trend_bias"].isin(self.VALID_BIAS_VALUES)]["htf_trend_bias"].unique()
            if len(invalid_values) > 0:
                raise DataQualityError(
                    f"Data quality validation failed: Invalid htf_trend_bias values: {invalid_values}"
                )
    
    def _validate_time_window_weight(self, df: pd.DataFrame) -> None:
        """
        Validate time window weight is in [0.0, 1.0].
        
        Args:
            df: DataFrame to validate
            
        Raises:
            DataQualityError: If time_window_weight out of range
        """
        if "time_window_weight" in df.columns:
            min_val = df["time_window_weight"].min()
            max_val = df["time_window_weight"].max()
            
            if min_val < 0.0:
                raise DataQualityError(
                    f"Data quality validation failed: time_window_weight has values below 0.0 (min: {min_val})"
                )
            if max_val > 1.0:
                raise DataQualityError(
                    f"Data quality validation failed: time_window_weight has values above 1.0 (max: {max_val})"
                )
    
    def _validate_close_position(self, df: pd.DataFrame) -> None:
        """
        Validate close position is in [0.0, 1.0].
        
        Args:
            df: DataFrame to validate
            
        Raises:
            DataQualityError: If close_position out of range
        """
        if "close_position" in df.columns:
            min_val = df["close_position"].min()
            max_val = df["close_position"].max()
            
            if min_val < 0.0:
                raise DataQualityError(
                    f"Data quality validation failed: close_position has values below 0.0 (min: {min_val})"
                )
            if max_val > 1.0:
                raise DataQualityError(
                    f"Data quality validation failed: close_position has values above 1.0 (max: {max_val})"
                )
