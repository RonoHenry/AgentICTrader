"""
Integration tests for the feature pipeline orchestration.

Tests the composition of HTFProjectionExtractor + CandleFeatureExtractor +
ZoneFeatureExtractor + SessionFeatureExtractor into a single sklearn Pipeline.

**Validates: Task 14 - Build sklearn feature pipeline orchestration**
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from ml.features.pipeline import FeaturePipeline


class TestFeaturePipeline:
    """Test suite for FeaturePipeline."""
    
    @pytest.fixture
    def sample_candles(self):
        """Create sample candle data for testing."""
        return [
            {
                "time": "2024-01-01T00:00:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5000,
                "high": 1.5100,
                "low": 1.4950,
                "close": 1.5080,
                "volume": 1000,
            },
            {
                "time": "2024-01-01T00:05:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5080,
                "high": 1.5090,
                "low": 1.5020,
                "close": 1.5030,
                "volume": 1200,
            },
            {
                "time": "2024-01-01T00:10:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5030,
                "high": 1.5150,
                "low": 1.5020,
                "close": 1.5140,
                "volume": 1500,
            },
        ]
    
    @pytest.fixture
    def sample_htf_candle(self):
        """Create sample HTF candle data for testing."""
        return {
            "time": "2024-01-01T00:00:00Z",
            "open": 1.5000,
            "high": 1.5200,
            "low": 1.4900,
            "close": 1.5180,
            "volume": 5000,
        }
    
    def test_pipeline_instantiation(self):
        """Test: FeaturePipeline instantiates successfully."""
        pipeline = FeaturePipeline()
        assert pipeline is not None
    
    def test_transform_returns_dataframe(self, sample_candles, sample_htf_candle):
        """Test: transform returns a pandas DataFrame."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        assert isinstance(result, pd.DataFrame)
    
    def test_transform_has_named_columns(self, sample_candles, sample_htf_candle):
        """Test: transform returns DataFrame with named columns."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        assert len(result.columns) > 0
        assert all(isinstance(col, str) for col in result.columns)
    
    def test_transform_includes_htf_projection_features(self, sample_candles, sample_htf_candle):
        """Test: transform includes HTF projection features."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        # Check for HTF projection columns
        expected_htf_cols = [
            "htf_timeframe",
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
        for col in expected_htf_cols:
            assert col in result.columns, f"Missing HTF column: {col}"
    
    def test_transform_includes_candle_features(self, sample_candles, sample_htf_candle):
        """Test: transform includes candle structure features."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        # Check for candle feature columns
        expected_candle_cols = [
            "body_pct",
            "upper_wick_pct",
            "lower_wick_pct",
            "close_position",
            "is_bullish",
        ]
        for col in expected_candle_cols:
            assert col in result.columns, f"Missing candle column: {col}"
    
    def test_transform_includes_zone_features(self, sample_candles, sample_htf_candle):
        """Test: transform includes zone and structure features."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        # Check for zone feature columns
        expected_zone_cols = [
            "bos_detected",
            "choch_detected",
            "fvg_present",
            "liquidity_sweep",
            "swing_high_distance",
            "swing_low_distance",
            "htf_trend_bias",
        ]
        for col in expected_zone_cols:
            assert col in result.columns, f"Missing zone column: {col}"
    
    def test_transform_includes_session_features(self, sample_candles, sample_htf_candle):
        """Test: transform includes session and time features."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        # Check for session feature columns
        expected_session_cols = [
            "time_window",
            "narrative_phase",
            "time_window_weight",
            "is_killzone",
            "is_high_probability_window",
        ]
        for col in expected_session_cols:
            assert col in result.columns, f"Missing session column: {col}"
    
    def test_fit_transform_returns_dataframe(self, sample_candles, sample_htf_candle):
        """Test: fit_transform returns a pandas DataFrame."""
        pipeline = FeaturePipeline()
        result = pipeline.fit_transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        assert isinstance(result, pd.DataFrame)
    
    def test_fit_transform_same_as_transform(self, sample_candles, sample_htf_candle):
        """Test: fit_transform produces same output as transform (stateless pipeline)."""
        pipeline = FeaturePipeline()
        
        result_fit_transform = pipeline.fit_transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        result_transform = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        # Compare column names
        assert list(result_fit_transform.columns) == list(result_transform.columns)
        
        # Compare values (allowing for floating point tolerance)
        pd.testing.assert_frame_equal(result_fit_transform, result_transform)


class TestFeaturePipelineDataQuality:
    """Test suite for Great Expectations data quality validations."""
    
    @pytest.fixture
    def sample_candles(self):
        """Create sample candle data for testing."""
        return [
            {
                "time": "2024-01-01T00:00:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5000,
                "high": 1.5100,
                "low": 1.4950,
                "close": 1.5080,
                "volume": 1000,
            },
            {
                "time": "2024-01-01T00:05:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5080,
                "high": 1.5090,
                "low": 1.5020,
                "close": 1.5030,
                "volume": 1200,
            },
            {
                "time": "2024-01-01T00:10:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5030,
                "high": 1.5150,
                "low": 1.5020,
                "close": 1.5140,
                "volume": 1500,
            },
        ]
    
    @pytest.fixture
    def sample_htf_candle(self):
        """Create sample HTF candle data for testing."""
        return {
            "time": "2024-01-01T00:00:00Z",
            "open": 1.5000,
            "high": 1.5200,
            "low": 1.4900,
            "close": 1.5180,
            "volume": 5000,
        }
    
    def test_no_nulls_in_htf_projection_columns(self, sample_candles, sample_htf_candle):
        """Test: validate no nulls in HTF projection columns."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        htf_cols = [
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
        
        for col in htf_cols:
            assert not result[col].isnull().any(), f"Null values found in {col}"
    
    def test_all_pct_values_in_valid_range(self, sample_candles, sample_htf_candle):
        """Test: all percentage values are in [0, 100]."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        pct_cols = [
            "htf_high_proximity_pct",
            "htf_low_proximity_pct",
            "htf_body_pct",
            "htf_upper_wick_pct",
            "htf_lower_wick_pct",
            "body_pct",
            "upper_wick_pct",
            "lower_wick_pct",
        ]
        
        for col in pct_cols:
            # Allow some tolerance for floating point arithmetic
            # and for proximity percentages which can exceed 100 when price is outside range
            if "proximity" not in col:
                assert result[col].min() >= -0.01, f"{col} has values below 0"
                assert result[col].max() <= 100.01, f"{col} has values above 100"
    
    def test_open_bias_in_valid_enum_set(self, sample_candles, sample_htf_candle):
        """Test: open_bias is in valid enum set (BULLISH, BEARISH, NEUTRAL)."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        valid_biases = {"BULLISH", "BEARISH", "NEUTRAL"}
        assert result["htf_open_bias"].isin(valid_biases).all(), \
            f"Invalid open_bias values: {result['htf_open_bias'].unique()}"
    
    def test_htf_trend_bias_in_valid_enum_set(self, sample_candles, sample_htf_candle):
        """Test: htf_trend_bias is in valid enum set (BULLISH, BEARISH, NEUTRAL)."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        valid_biases = {"BULLISH", "BEARISH", "NEUTRAL"}
        assert result["htf_trend_bias"].isin(valid_biases).all(), \
            f"Invalid htf_trend_bias values: {result['htf_trend_bias'].unique()}"
    
    def test_time_window_weight_in_valid_range(self, sample_candles, sample_htf_candle):
        """Test: time_window_weight is in [0.0, 1.0]."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        assert result["time_window_weight"].min() >= 0.0, \
            "time_window_weight has values below 0.0"
        assert result["time_window_weight"].max() <= 1.0, \
            "time_window_weight has values above 1.0"
    
    def test_close_position_in_valid_range(self, sample_candles, sample_htf_candle):
        """Test: close_position is in [0.0, 1.0]."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        assert result["close_position"].min() >= 0.0, \
            "close_position has values below 0.0"
        assert result["close_position"].max() <= 1.0, \
            "close_position has values above 1.0"
    
    def test_boolean_columns_are_boolean(self, sample_candles, sample_htf_candle):
        """Test: boolean columns contain only True/False values."""
        pipeline = FeaturePipeline()
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        
        boolean_cols = [
            "is_bullish",
            "bos_detected",
            "choch_detected",
            "fvg_present",
            "liquidity_sweep",
            "is_killzone",
            "is_high_probability_window",
        ]
        
        for col in boolean_cols:
            assert result[col].dtype == bool or result[col].isin([0, 1, True, False]).all(), \
                f"{col} contains non-boolean values"


class TestFeaturePipelineWithRealData:
    """Integration tests using real candle data from TimescaleDB."""
    
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires TimescaleDB connection - run manually")
    def test_pipeline_with_100_real_candles(self):
        """Test: pipeline processes 100 real candles from TimescaleDB."""
        # This test would connect to TimescaleDB and fetch 100 real candles
        # For now, we skip it as it requires database setup
        # TODO: Implement when TimescaleDB is available in test environment
        pass
    
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires TimescaleDB connection - run manually")
    def test_pipeline_performance_benchmark(self):
        """Test: pipeline processes 100 candles in < 1 second."""
        # This test would benchmark the pipeline performance
        # TODO: Implement when TimescaleDB is available in test environment
        pass


class TestFeaturePipelineValidation:
    """Test suite for data quality validation methods."""
    
    @pytest.fixture
    def sample_candles(self):
        """Create sample candle data for testing."""
        return [
            {
                "time": "2024-01-01T00:00:00Z",
                "instrument": "EURUSD",
                "timeframe": "M5",
                "open": 1.5000,
                "high": 1.5100,
                "low": 1.4950,
                "close": 1.5080,
                "volume": 1000,
            },
        ]
    
    @pytest.fixture
    def sample_htf_candle(self):
        """Create sample HTF candle data for testing."""
        return {
            "time": "2024-01-01T00:00:00Z",
            "open": 1.5000,
            "high": 1.5200,
            "low": 1.4900,
            "close": 1.5180,
            "volume": 5000,
        }
    
    def test_validation_can_be_disabled(self, sample_candles, sample_htf_candle):
        """Test: validation can be disabled for performance-critical paths."""
        pipeline = FeaturePipeline(enable_validation=False)
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        assert isinstance(result, pd.DataFrame)
    
    def test_validation_passes_for_valid_data(self, sample_candles, sample_htf_candle):
        """Test: validation passes for valid data."""
        pipeline = FeaturePipeline(enable_validation=True)
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        # Should not raise any exception
        assert isinstance(result, pd.DataFrame)
    
    def test_validate_data_quality_method_exists(self):
        """Test: validate_data_quality method exists and is callable."""
        pipeline = FeaturePipeline()
        assert hasattr(pipeline, "validate_data_quality")
        assert callable(pipeline.validate_data_quality)
    
    def test_validate_data_quality_returns_true_for_valid_data(self, sample_candles, sample_htf_candle):
        """Test: validate_data_quality returns True for valid data."""
        pipeline = FeaturePipeline(enable_validation=False)
        result = pipeline.transform(
            candles=sample_candles,
            htf_candle=sample_htf_candle,
            instrument="EURUSD",
        )
        assert pipeline.validate_data_quality(result) is True
