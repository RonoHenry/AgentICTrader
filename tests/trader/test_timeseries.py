import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

class TestTimeseriesInfrastructure:

    def test_write_and_query_ohlcv_data(self, write_api, query_api):
        """Test writing and querying OHLCV data"""
        # Create test data point
        point = Point("BTCUSDT")\
            .tag("exchange", "binance")\
            .tag("market_type", "spot")\
            .field("open", 45000.0)\
            .field("high", 46000.0)\
            .field("low", 44500.0)\
            .field("close", 45500.0)\
            .field("volume", 100.5)\
            .time(datetime.now(timezone.utc))

        # Write data
        write_api.write(bucket="test_bucket", record=point)

        # Query data
        query = f'''
        from(bucket: "test_bucket")
            |> range(start: -1h)
            |> filter(fn: (r) => r["_measurement"] == "BTCUSDT")
            |> filter(fn: (r) => r["exchange"] == "binance")
            |> filter(fn: (r) => r["market_type"] == "spot")
        '''
        result = query_api.query(query)

        # Verify results
        assert len(result) > 0, "No data found"
        
        # Get the first table and record
        table = result[0]
        record = table.records[0]
        
        # Verify fields
        assert record.get_field() in ["open", "high", "low", "close", "volume"]
        assert record.get_value() in [45000.0, 46000.0, 44500.0, 45500.0, 100.5]
