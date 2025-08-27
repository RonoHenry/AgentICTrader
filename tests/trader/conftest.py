import pytest
from unittest.mock import MagicMock, patch
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

@pytest.fixture(scope="class")
def mock_influx_client():
    """Create a mock InfluxDB client for testing"""
    with patch('influxdb_client.InfluxDBClient') as mock_client:
        client = MagicMock()
        mock_client.return_value = client
        yield client

@pytest.fixture(scope="class")
def mock_write_api(mock_influx_client):
    """Get mock write API"""
    write_api = MagicMock()
    mock_influx_client.write_api.return_value = write_api
    return write_api

@pytest.fixture(scope="class")
def mock_query_api(mock_influx_client):
    """Get mock query API"""
    query_api = MagicMock()
    mock_influx_client.query_api.return_value = query_api
    return query_api
