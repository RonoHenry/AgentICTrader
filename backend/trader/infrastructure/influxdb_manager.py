"""
InfluxDB Manager for handling all InfluxDB operations.
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone
from django.conf import settings
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.client.exceptions import InfluxDBError

class InfluxDBManager:
    """Manages all InfluxDB operations including connections, buckets, and data operations."""

    def __init__(self):
        """Initialize InfluxDB manager with configuration from settings."""
        self.config = self.get_connection_config()
        self._client = None

    def get_connection_config(self) -> Dict[str, str]:
        """
        Get InfluxDB connection configuration from Django settings.
        
        Returns:
            Dict containing url, token, org, and default_bucket
        """
        return {
            'url': settings.INFLUXDB_URL,
            'token': settings.INFLUXDB_TOKEN,
            'org': settings.INFLUXDB_ORG,
            'default_bucket': settings.INFLUXDB_DEFAULT_BUCKET
        }

    def get_client(self) -> InfluxDBClient:
        """
        Get or create InfluxDB client instance.
        
        Returns:
            InfluxDBClient instance
        """
        if not self._client:
            self._client = InfluxDBClient(
                url=self.config['url'],
                token=self.config['token'],
                org=self.config['org']
            )
        return self._client

    def create_bucket_structure(self) -> List[str]:
        """
        Create the required bucket structure for different timeframes.
        
        Returns:
            List of created bucket names
        """
        buckets = [
            "market_data_m1",
            "market_data_m5",
            "market_data_m15",
            "market_data_h1",
            "market_data_h4",
            "market_data_d1",
        ]
        
        client = self.get_client()
        buckets_api = client.buckets_api()
        
        for bucket in buckets:
            if not self.bucket_exists(bucket):
                buckets_api.create_bucket(bucket_name=bucket, org=self.config['org'])
        
        return buckets

    def bucket_exists(self, bucket_name: str) -> bool:
        """
        Check if a bucket exists.
        
        Args:
            bucket_name: Name of the bucket to check
            
        Returns:
            bool indicating if bucket exists
        """
        client = self.get_client()
        buckets_api = client.buckets_api()
        buckets = buckets_api.find_buckets().buckets
        return any(b.name == bucket_name for b in buckets)

    def set_retention_policy(self, bucket_name: str, duration: str) -> None:
        """
        Set retention policy for a bucket.
        
        Args:
            bucket_name: Name of the bucket
            duration: Duration string (e.g., '7d', '30d', '365d')
            
        Raises:
            ValueError: If duration format is invalid
            InfluxDBError: If bucket does not exist or update fails
        """
        # Validate duration format
        if not any(duration.endswith(unit) for unit in ['d', 'h', 'm', 's']):
            raise ValueError("Invalid duration format. Must end with d, h, m, or s")
            
        try:
            value = int(duration[:-1])
            if value <= 0:
                raise ValueError("Duration value must be positive")
        except ValueError as e:
            raise ValueError(f"Invalid duration format: {str(e)}")
        
        client = self.get_client()
        buckets_api = client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        
        if bucket:
            buckets_api.update_bucket_retention_rules(
                bucket_id=bucket.id,
                rules=[{"type": "expire", "everySeconds": self._parse_duration(duration)}]
            )
        else:
            raise InfluxDBError(f"Bucket {bucket_name} does not exist")

    def get_retention_policy(self, bucket_name: str) -> Optional[str]:
        """
        Get retention policy duration for a bucket.
        
        Args:
            bucket_name: Name of the bucket
            
        Returns:
            Duration string or None if no retention policy exists
        """
        client = self.get_client()
        buckets_api = client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        
        if bucket and bucket.retention_rules:
            seconds = bucket.retention_rules[0].every_seconds
            return self._format_duration(seconds)
        return None

    def write_point(self, bucket: str, data: Dict) -> None:
        """
        Write a data point to specified bucket.
        
        Args:
            bucket: Name of the bucket
            data: Dictionary containing point data
            
        Raises:
            ValueError: If bucket name is empty or data format is invalid
        """
        if not bucket:
            raise ValueError("Bucket name cannot be empty")
            
        if "symbol" not in data:
            raise KeyError("Data must contain 'symbol' field")
        
        client = self.get_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Extract timestamp if present
        timestamp = data.pop("timestamp", datetime.now(timezone.utc))
        
        # Create InfluxDB point
        point = Point("market_data")\
            .tag("symbol", data["symbol"])\
            .time(timestamp)
            
        # Add all other fields except symbol
        for key, value in data.items():
            if key != "symbol":
                point = point.field(key, value)
        
        write_api.write(
            bucket=bucket,
            org=self.config['org'],
            record=point
        )

    def query_last_point(self, bucket: str, symbol: str) -> Optional[Dict]:
        """
        Query the last point for a symbol from specified bucket.
        
        Args:
            bucket: Name of the bucket
            symbol: Symbol to query for
            
        Returns:
            Dictionary containing point data or None if no data exists
        """
        client = self.get_client()
        query_api = client.query_api()
        
        query = f'''
            from(bucket: "{bucket}")
                |> range(start: -1h)
                |> filter(fn: (r) => r["symbol"] == "{symbol}")
                |> last()
        '''
        
        result = query_api.query(query=query, org=self.config['org'])
        
        if result and len(result) > 0 and len(result[0].records) > 0:
            return result[0].records[0].values
        return None

    def query_range(self, bucket: str, symbol: str, start: datetime, end: Optional[datetime] = None,
                 fields: Optional[List[str]] = None) -> List[Dict]:
        """
        Query data points for a symbol within a time range.
        
        Args:
            bucket: Name of the bucket
            symbol: Symbol to query for
            start: Start time of the range
            end: Optional end time, defaults to now
            fields: Optional list of fields to return
            
        Returns:
            List of data points
        """
        client = self.get_client()
        query_api = client.query_api()
        
        # Format times
        start_str = start.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%SZ') if end else 'now()'
        
        # Build field filter if needed
        field_filter = ''
        if fields:
            field_list = '", "'.join(fields)
            field_filter = f'|> keep(columns: ["_time", "_value", "_field", "symbol"])\n'
            field_filter += f'|> filter(fn: (r) => contains(value: r._field, set: ["{field_list}"]))\n'
        
        query = f'''
            from(bucket: "{bucket}")
                |> range(start: {start_str}, stop: {end_str})
                |> filter(fn: (r) => r["symbol"] == "{symbol}")
                {field_filter}
                |> sort(columns: ["_time"])
        '''
        
        result = query_api.query(query=query, org=self.config['org'])
        
        points = []
        for table in result:
            for record in table.records:
                point_data = {
                    "timestamp": record.get_time(),
                    "symbol": record.values.get("symbol"),
                    record.get_field(): record.get_value()
                }
                points.append(point_data)
        
        return points

    def _parse_duration(self, duration: str) -> int:
        """Convert duration string to seconds."""
        unit = duration[-1]
        value = int(duration[:-1])
        
        if unit == 'd':
            return value * 24 * 60 * 60
        elif unit == 'h':
            return value * 60 * 60
        elif unit == 'm':
            return value * 60
        return value

    def _format_duration(self, seconds: int) -> str:
        """
        Convert seconds to duration string.
        Tries to use the most granular unit possible.
        E.g. 86400 -> "24h" instead of "1d"
        """
        if seconds == 0:
            return "0s"
        
        if seconds % 60 != 0:
            return f"{seconds}s"
        
        minutes = seconds // 60
        if minutes < 60 or minutes % 60 != 0:
            return f"{minutes}m"
        
        hours = minutes // 60
        if hours < 24 or hours % 24 != 0:
            return f"{hours}h"
        
        days = hours // 24
        return f"{days}d"
