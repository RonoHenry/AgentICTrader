"""
Time series data management using InfluxDB.
"""
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import dataclass
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

@dataclass
class OHLCVPoint:
    """Represents a single OHLCV data point."""
    symbol: str
    timestamp: datetime
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self):
        """Validate the OHLCVPoint data."""
        if not self.symbol:
            raise ValueError("Symbol cannot be empty")

        if not self.timeframe:
            raise ValueError("Timeframe cannot be empty")

        if not isinstance(self.timestamp, datetime):
            raise ValueError("Timestamp must be a datetime object")

        if not all(isinstance(price, Decimal) for price in [self.open, self.high, self.low, self.close]):
            raise ValueError("Price values must be Decimal type")

        if not isinstance(self.volume, int):
            raise ValueError("Volume must be an integer")

        if self.volume < 0:
            raise ValueError("Volume must be non-negative")

        if self.high < self.low:
            raise ValueError("High price must be greater than or equal to low price")

        if not self.low <= self.open <= self.high:
            raise ValueError("Open price must be within high-low range")

        if not self.low <= self.close <= self.high:
            raise ValueError("Close price must be within high-low range")

    def to_influx_point(self) -> Point:
        """Convert to InfluxDB point."""
        return (
            Point("ohlcv")
            .tag("symbol", self.symbol)
            .tag("timeframe", self.timeframe)
            .field("open", float(self.open))
            .field("high", float(self.high))
            .field("low", float(self.low))
            .field("close", float(self.close))
            .field("volume", self.volume)
            .time(self.timestamp, WritePrecision.NS)
        )

class TimeseriesBucket:
    """Manages InfluxDB bucket operations."""
    
    def __init__(self, client: InfluxDBClient, name: str):
        self.client = client
        self.name = name
        self._bucket = None
        
    @classmethod
    def create(cls, client: InfluxDBClient, name: str, retention_days: int) -> 'TimeseriesBucket':
        """Create a new bucket with retention policy."""
        retention = f"{retention_days}d"
        buckets_api = client.buckets_api()
        org = client.org
        
        # Create bucket if it doesn't exist
        bucket = buckets_api.find_bucket_by_name(name)
        if not bucket:
            bucket = buckets_api.create_bucket(
                bucket_name=name,
                org=org,
                retention_rules=[{"type": "expire", "everySeconds": retention_days * 86400}]
            )
            
        return cls(client=client, name=name)
        
    def exists(self) -> bool:
        """Check if bucket exists."""
        return self.client.buckets_api().find_bucket_by_name(self.name) is not None
        
    def get_retention_period(self) -> str:
        """Get bucket retention period."""
        bucket = self.client.buckets_api().find_bucket_by_name(self.name)
        if bucket and bucket.retention_rules:
            seconds = bucket.retention_rules[0].every_seconds
            return f"{seconds // 86400}d"
        return "infinite"

class TimeseriesManager:
    """Manages time series data operations."""
    
    def __init__(self, client: InfluxDBClient):
        self.client = client
        self.write_api = client.write_api(write_options=SYNCHRONOUS)
        self.query_api = client.query_api()
        
    def write_ohlcv(self, data: OHLCVPoint) -> bool:
        """Write OHLCV data point."""
        try:
            point = data.to_influx_point()
            self.write_api.write(
                bucket="market_data",
                org=self.client.org,
                record=point
            )
            return True
        except Exception as e:
            print(f"Error writing data: {e}")
            return False
            
    def read_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[OHLCVPoint]:
        """Read OHLCV data points."""
        # Ensure times are timezone-aware
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
            
        # Add a small buffer to avoid empty range
        query_start = start_time - timedelta(minutes=1)
        query_end = end_time + timedelta(minutes=1)
            
        query = f'''
            from(bucket: "market_data")
                |> range(start: {query_start.isoformat()}, stop: {query_end.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "ohlcv")
                |> filter(fn: (r) => r["symbol"] == "{symbol}")
                |> filter(fn: (r) => r["timeframe"] == "{timeframe}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> filter(fn: (r) => r["_time"] >= {start_time.isoformat()})
                |> filter(fn: (r) => r["_time"] <= {end_time.isoformat()})
        '''
        
        result = self.query_api.query(query=query, org=self.client.org)
        points = []
        
        for table in result:
            for record in table.records:
                point = OHLCVPoint(
                    symbol=record.values.get("symbol"),
                    timestamp=record.values.get("_time"),
                    timeframe=record.values.get("timeframe"),
                    open=Decimal(str(record.values.get("open"))),
                    high=Decimal(str(record.values.get("high"))),
                    low=Decimal(str(record.values.get("low"))),
                    close=Decimal(str(record.values.get("close"))),
                    volume=int(record.values.get("volume"))
                )
                points.append(point)
                
        return points
        
    def get_bucket(self, name: str) -> TimeseriesBucket:
        """Get a bucket by name."""
        return TimeseriesBucket(client=self.client, name=name)
