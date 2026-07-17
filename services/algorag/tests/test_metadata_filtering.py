"""
Tests for metadata filtering functionality (Task 10.2).

Tests that Qdrant filter construction works correctly from request parameters
and handles optional filters properly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from qdrant_client.http import models as qmodels

from services.algorag.models import RetrievalRequest


class TestMetadataFiltering:
    """Tests for metadata filtering in retrieval endpoint."""

    def test_build_filter_all_required_fields(self):
        """RED: Test filtering by instrument, time_window, htf_open_bias, outcome_result=WIN."""
        # Setup request with all filter parameters
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="LONDON_KILLZONE",
            htf_open_bias="BULLISH", 
            outcome_filter="WIN"
        )

        # Import the filter building function (will implement in GREEN phase)
        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify: filter should have 4 must conditions
        assert isinstance(qdrant_filter, qmodels.Filter)
        assert qdrant_filter.must is not None
        assert len(qdrant_filter.must) == 4

        # Verify each condition
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "EURUSD"
        assert conditions["time_window"] == "LONDON_KILLZONE"
        assert conditions["htf_open_bias"] == "BULLISH"
        assert conditions["outcome_result"] == "WIN"

    def test_build_filter_required_only(self):
        """RED: Test filtering with only required instrument field."""
        request = RetrievalRequest(
            instrument="GBPUSD",
            timestamp=datetime.now(timezone.utc),
        )

        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify: filter should have 2 must conditions (instrument + outcome_filter default)
        assert isinstance(qdrant_filter, qmodels.Filter)
        assert qdrant_filter.must is not None
        assert len(qdrant_filter.must) == 2

        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "GBPUSD"
        assert conditions["outcome_result"] == "WIN"  # Default value

    def test_build_filter_optional_fields(self):
        """RED: Test optional filters (allow missing parameters)."""
        # Test with some optional fields present
        request = RetrievalRequest(
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="NY_KILLZONE",
            # htf_open_bias and outcome_filter are None
        )

        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify: filter should have 3 must conditions (instrument + time_window + outcome_filter default)
        assert len(qdrant_filter.must) == 3

        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "XAUUSD"
        assert conditions["time_window"] == "NY_KILLZONE"
        assert conditions["outcome_result"] == "WIN"  # Default value
        # htf_open_bias should not be present
        assert "htf_open_bias" not in conditions

    def test_build_filter_no_outcome_filter(self):
        """RED: Test filtering when outcome_filter is None (should return all outcomes)."""
        request = RetrievalRequest(
            instrument="USDJPY",
            timestamp=datetime.now(timezone.utc),
            outcome_filter=None  # Explicitly set to None
        )

        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify: outcome_result should not be in filter conditions
        assert len(qdrant_filter.must) == 1
        condition = qdrant_filter.must[0]
        assert condition.key == "instrument"
        assert condition.match.value == "USDJPY"

    def test_build_filter_empty_string_treated_as_none(self):
        """RED: Test that empty strings are treated as None for optional filters."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="",  # Empty string should be treated as None
            htf_open_bias="",  # Empty string should be treated as None
            outcome_filter=""  # Empty string should be treated as None
        )

        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify: only instrument filter should be present
        assert len(qdrant_filter.must) == 1
        condition = qdrant_filter.must[0]
        assert condition.key == "instrument"
        assert condition.match.value == "EURUSD"

    def test_build_filter_case_sensitivity(self):
        """RED: Test that instrument is properly uppercased but other fields preserve case."""
        request = RetrievalRequest(
            instrument="eurusd",  # Should be converted to uppercase
            timestamp=datetime.now(timezone.utc),
            time_window="London_Killzone",  # Should preserve case
            htf_open_bias="bullish",  # Should preserve case as specified
            outcome_filter="win"  # Should preserve case as specified
        )

        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify conditions
        conditions = {cond.key: cond.match.value for cond in qdrant_filter.must}
        assert conditions["instrument"] == "EURUSD"  # Uppercased
        assert conditions["time_window"] == "London_Killzone"  # Case preserved
        assert conditions["htf_open_bias"] == "bullish"  # Case preserved
        assert conditions["outcome_result"] == "win"  # Case preserved

    @pytest.mark.integration
    async def test_filter_integration_with_search(self):
        """RED: Test that filters work correctly in actual Qdrant search."""
        from services.algorag.qdrant_client import QdrantClientWrapper
        from qdrant_client.http import models as qmodels
        import numpy as np

        # Setup mock Qdrant client
        mock_client = AsyncMock()
        mock_search_result = [
            MagicMock(
                payload={
                    "trade_id": "TRD-001",
                    "instrument": "EURUSD",
                    "time_window": "LONDON_KILLZONE",
                    "htf_open_bias": "BULLISH",
                    "outcome_result": "WIN",
                    "outcome_r_multiple": 3.5,
                    "narrative": "Test setup"
                },
                score=0.85
            )
        ]
        mock_client.search.return_value = mock_search_result

        with patch('services.algorag.qdrant_client.QdrantClientWrapper.get_client', return_value=mock_client):
            wrapper = QdrantClientWrapper()
            
            # Create request
            request = RetrievalRequest(
                instrument="EURUSD",
                timestamp=datetime.now(timezone.utc),
                time_window="LONDON_KILLZONE",
                htf_open_bias="BULLISH",
                outcome_filter="WIN"
            )

            from services.algorag.filtering import build_qdrant_filter

            # Build filter
            qdrant_filter = build_qdrant_filter(request)
            
            # Execute search with filter
            query_vector = np.zeros(528).tolist()
            results = await wrapper.search(
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=10
            )

            # Verify search was called with correct filter
            mock_client.search.assert_called_once()
            call_args = mock_client.search.call_args
            
            assert call_args.kwargs["query_filter"] == qdrant_filter
            assert call_args.kwargs["query_vector"] == query_vector
            assert call_args.kwargs["limit"] == 10

    def test_filter_validation_with_invalid_instrument(self):
        """RED: Test that empty instrument raises validation error."""
        with pytest.raises(ValueError, match="instrument"):
            RetrievalRequest(
                instrument="",  # Empty instrument should fail validation
                timestamp=datetime.now(timezone.utc),
            )

    def test_filter_field_condition_structure(self):
        """RED: Test that FieldCondition objects are created with correct structure."""
        request = RetrievalRequest(
            instrument="EURUSD",
            timestamp=datetime.now(timezone.utc),
            time_window="LONDON_KILLZONE"
        )

        from services.algorag.filtering import build_qdrant_filter

        # Execute
        qdrant_filter = build_qdrant_filter(request)

        # Verify each condition is a FieldCondition with MatchValue
        for condition in qdrant_filter.must:
            assert isinstance(condition, qmodels.FieldCondition)
            assert isinstance(condition.match, qmodels.MatchValue)
            assert condition.key in ["instrument", "time_window", "htf_open_bias", "outcome_result"]
            assert isinstance(condition.match.value, str)