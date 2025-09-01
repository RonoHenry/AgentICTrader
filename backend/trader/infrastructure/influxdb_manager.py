"""
InfluxDB Manager for handling all InfluxDB operations.
"""
import http.client
import json
from typing import Dict, List, Optional, Union
import time
from datetime import datetime, timezone, timedelta
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

    def create_bucket(self, bucket_name: str, retention_hours: Optional[int] = None) -> Optional[object]:
        """
        Create a new bucket.
        
        Args:
            bucket_name: Name of the bucket to create
            retention_hours: Optional retention period in hours
            
        Returns:
            Created bucket object or None if creation fails
            
        Raises:
            ValueError: If bucket name is empty
            InfluxDBError: If bucket already exists
        """
        if not bucket_name:
            raise ValueError("Bucket name cannot be empty")
            
        client = self.get_client()
        buckets_api = client.buckets_api()
        
        # Check if bucket exists
        if buckets_api.find_bucket_by_name(bucket_name):
            # Create mock response for error
            raise InfluxDBError(message=f"bucket with name {bucket_name} already exists")
            
        # Create bucket with retention policy if specified
        retention_rules = []
        if retention_hours:
            retention_rules = [{"type": "expire", "everySeconds": retention_hours * 3600}]
            
        bucket = buckets_api.create_bucket(
            bucket_name=bucket_name,
            org=self.config['org'],
            retention_rules=retention_rules
        )
        
        return bucket

    def delete_bucket(self, bucket_name: str) -> None:
        """
        Delete a bucket.
        
        Args:
            bucket_name: Name of the bucket to delete
            
        Raises:
            InfluxDBError: If bucket does not exist
        """
        client = self.get_client()
        buckets_api = client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        
        if bucket:
            buckets_api.delete_bucket(bucket)
        else:
            raise InfluxDBError(f"Bucket {bucket_name} does not exist")
            
    def create_bucket_structure(self) -> List[str]:
        """
        Create or update the required bucket structure for different timeframes.
        
        Returns:
            List of created/updated bucket names
        """
        bucket_configs = [
            ("market_data_m1", 7 * 24),      # 1-minute data, keep for 1 week
            ("market_data_m5", 14 * 24),     # 5-minute data, keep for 2 weeks
            ("market_data_m15", 30 * 24),    # 15-minute data, keep for 1 month
            ("market_data_h1", 90 * 24),     # 1-hour data, keep for 3 months
            ("market_data_h4", 180 * 24),    # 4-hour data, keep for 6 months
            ("market_data_d1", 365 * 24),    # Daily data, keep for 1 year
        ]
        
        # First delete all existing buckets to ensure clean state
        client = self.get_client()
        buckets_api = client.buckets_api()
        existing_buckets = buckets_api.find_buckets().buckets
        for bucket in existing_buckets:
            try:
                if bucket.name in [name for name, _ in bucket_configs]:
                    buckets_api.delete_bucket(bucket)
                    time.sleep(0.1)  # Wait a bit to ensure deletion
            except Exception as e:
                pass  # Ignore errors when bucket doesn't exist or can't be deleted

        # Create fresh buckets with retention policies
        buckets = []
        for bucket_name, retention_hours in bucket_configs:
            # Create bucket with retention rules
            retention_rules = [{"type": "expire", "everySeconds": retention_hours * 3600}]
            # Debug output
            print(f"\nCreating bucket {bucket_name} with retention {retention_hours}h ({retention_hours/24} days)")
            print(f"Rules: {retention_rules}")
            bucket = buckets_api.create_bucket(
                bucket_name=bucket_name,
                org=self.config['org'],
                retention_rules=retention_rules
            )
            print(f"Created bucket {bucket_name}: {bucket.retention_rules}")
            buckets.append(bucket_name)
            time.sleep(0.1)  # Wait a bit between creations
        
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
            # Update retention rules
            bucket.retention_rules = [{"type": "expire", "everySeconds": self._parse_duration(duration)}]
            buckets_api.update_bucket(bucket)
        else:
            raise InfluxDBError(f"Bucket {bucket_name} does not exist")

    def get_retention_policy(self, bucket_name: str, return_str: bool = False) -> Union[timedelta, str]:
        """
        Get retention policy duration for a bucket.
        
        Args:
            bucket_name: Name of the bucket
            return_str: If True, returns duration as string (e.g. "7d"), else as timedelta
            
        Returns:
            Duration as timedelta or string depending on return_str
        """
        client = self.get_client()
        buckets_api = client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        
        print(f"\nGetting retention policy for {bucket_name}:")
        print(f"Bucket: {bucket}")
        print(f"Rules: {bucket.retention_rules if bucket and bucket.retention_rules else 'None'}")
        
        if bucket and bucket.retention_rules and len(bucket.retention_rules) > 0:
            rule = bucket.retention_rules[0]
            # Extract retention rule
            if isinstance(rule, dict):
                if 'everySeconds' in rule:
                    seconds = rule['everySeconds']
                else:
                    seconds = rule.get('every_seconds', 0)
            else:
                if hasattr(rule, 'everySeconds'):
                    seconds = rule.everySeconds
                else:
                    seconds = getattr(rule, 'every_seconds', 0)

            print(f"Seconds: {seconds} ({seconds/(24*3600)} days)")
            if seconds:
                if return_str:
                    return self._format_duration(seconds)
                return timedelta(seconds=seconds)
            if return_str:
                return "0s"
            return timedelta(0)
        
    def delete_bucket(self, bucket_name: str) -> None:
        """
        Delete a bucket.
        
        Args:
            bucket_name: Name of the bucket to delete
            
        Raises:
            InfluxDBError: If bucket does not exist or deletion fails
        """
        client = self.get_client()
        buckets_api = client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        
        if bucket:
            buckets_api.delete_bucket(bucket=bucket)
        else:
            # Create mock response for error
            raise InfluxDBError(message=f"bucket {bucket_name} not found")

    def write_point(self, bucket: str, data: Dict) -> bool:
        """
        Write a data point to specified bucket.
        
        Args:
            bucket: Name of the bucket
            data: Dictionary containing point data
            
        Returns:
            bool indicating success of write operation
            
        Raises:
            ValueError: If bucket name is empty or data format is invalid
        """
        if not bucket:
            raise ValueError("Bucket name cannot be empty")
            
        if "symbol" not in data:
            raise KeyError("Data must contain 'symbol' field")
        
        client = self.get_client()
        
        # Create bucket if it doesn't exist
        if not self.bucket_exists(bucket):
            try:
                self.create_bucket(bucket)
            except Exception as e:
                print(f"Failed to create bucket {bucket}: {str(e)}")
                return False
        
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Extract timestamp if present
        timestamp = data.pop("timestamp", datetime.now(timezone.utc))
        
        # Create InfluxDB point
        point = Point("market_data")\
            .tag("symbol", data["symbol"])\
            .time(timestamp)
            
        # Add numeric fields except symbol and timestamp
        for key, value in data.items():
            if key not in ["symbol", "timestamp"]:
                try:
                    # Convert to float for numeric fields
                    float_value = float(value)
                    point = point.field(key, float_value)
                except (TypeError, ValueError):
                    # Skip non-numeric values
                    print(f"Skipping non-numeric field {key}: {value}")
                    continue
        
        try:
            write_api.write(
                bucket=bucket,
                org=self.config['org'],
                record=point
            )
            return True
        except Exception as e:
            print(f"Failed to write point to bucket {bucket}: {str(e)}")
            return False

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
                |> filter(fn: (r) => r._measurement == "market_data" and r.symbol == "{symbol}")
                |> last()
                |> pivot(rowKey: ["_time", "symbol"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        result = query_api.query(query=query, org=self.config['org'])
        
        if result and len(result) > 0 and len(result[0].records) > 0:
            record = result[0].records[0]
            return {
                "timestamp": record.get_time(),
                "symbol": record.values.get("symbol"),
                "open": float(record.values.get("open", 0)),
                "high": float(record.values.get("high", 0)),
                "low": float(record.values.get("low", 0)),
                "close": float(record.values.get("close", 0)),
                "volume": float(record.values.get("volume", 0))
            }
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
        Always uses the largest unit possible.
        E.g. 86400 -> "1d" instead of "24h"
        """
        if seconds == 0:
            return "0s"

        # Convert to days if evenly divisible by days
        one_day = 24 * 60 * 60
        if seconds >= one_day and seconds % one_day == 0:
            days = seconds // one_day
            return f"{days}d"
        
        # Convert to hours if >= 1 hour and evenly divisible by hours
        one_hour = 60 * 60
        if seconds >= one_hour and seconds % one_hour == 0:
            hours = seconds // one_hour
            if hours >= 24:  # Convert to days if 24 hours or more
                days = hours // 24
                return f"{days}d"
            return f"{hours}h"
        
        # Convert to minutes if >= 1 minute and evenly divisible by minutes
        if seconds >= 60 and seconds % 60 == 0:
            minutes = seconds // 60
            if minutes >= 60:  # Convert to hours if 60 minutes or more
                hours = minutes // 60
                if hours >= 24:  # Convert to days if 24 hours or more
                    days = hours // 24
                    return f"{days}d"
                return f"{hours}h"
            return f"{minutes}m"
        
        return f"{seconds}s"
