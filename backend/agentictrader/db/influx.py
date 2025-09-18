"""
InfluxDB client for AgentICTrader.
"""
from influxdb_client import InfluxDBClient, WriteOptions
from ..config import INFLUXDB_CONFIG

class InfluxDBConnection:
    """
    InfluxDB connection manager. Creates a singleton instance of the InfluxDB client.
    """
    _instance = None

    @classmethod
    def get_client(cls):
        """Get the singleton instance of InfluxDBClient."""
        if cls._instance is None:
            url = f"http://{INFLUXDB_CONFIG['host']}:{INFLUXDB_CONFIG['port']}"
            cls._instance = InfluxDBClient(
                url=url,
                token=INFLUXDB_CONFIG['token'],
                org=INFLUXDB_CONFIG['org'],
            )
        return cls._instance

    @classmethod
    def get_write_api(cls, write_options=None):
        """Get a write API client with optional write options."""
        if write_options is None:
            write_options = WriteOptions(
                batch_size=1000,
                flush_interval=10_000,  # 10 seconds
                jitter_interval=2_000,  # 2 seconds
                retry_interval=5_000,   # 5 seconds
                max_retries=5,
                max_retry_delay=30_000, # 30 seconds
                exponential_base=2
            )
        return cls.get_client().write_api(write_options=write_options)

    @classmethod
    def get_query_api(cls):
        """Get a query API client."""
        return cls.get_client().query_api()

    @classmethod
    def close(cls):
        """Close the client connection."""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

    def __new__(cls):
        """Prevent instantiation of this class."""
        raise TypeError("InfluxDBConnection should not be instantiated. Use InfluxDBConnection.get_client() instead.")
