"""
Test configuration for infrastructure tests.
"""
import pytest
import os
import requests
from influxdb_client import InfluxDBClient
from django.conf import settings
from pytest_docker.plugin import Services

@pytest.fixture(scope="session")
def docker_compose_file():
    """Get docker-compose.test.yml path."""
    docker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../docker"))
    return os.path.join(docker_dir, "docker-compose.test.yml")

@pytest.fixture(scope="session")
def influxdb_service(docker_ip, docker_services):
    """Start InfluxDB container and wait for it to be ready."""
    # Get port mapping and service URL
    port = docker_services.port_for("influxdb", 8086)
    url = f"http://{docker_ip}:{port}"
    
    def is_responsive():
        try:
            # Try to reach the InfluxDB health endpoint
            response = requests.get(f"{url}/health")
            return response.status_code == 200
        except:
            return False

    # Wait for service to be responsive
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.1,
        check=lambda: is_responsive()
    )
    return url

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
