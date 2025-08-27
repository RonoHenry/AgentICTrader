"""
Test configuration for infrastructure tests.
"""
import pytest
from influxdb_client import InfluxDBClient
from pytest_docker.plugin import Services

@pytest.fixture(scope="session")
def influxdb_service(docker_ip, docker_services):
    """Start InfluxDB container and wait for it to be ready."""
    port = docker_services.port_for("influxdb", 8086)
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1,
        check=lambda: docker_services.is_responsive(host=docker_ip, port=port)
    )
    return f"http://{docker_ip}:{port}"

@pytest.fixture
def influx_client(influxdb_service):
    """Create an InfluxDB client for testing."""
    client = InfluxDBClient(
        url=influxdb_service,
        token="test-token",
        org="agentic"
    )
    yield client
    client.close()
