import os
import subprocess
import sys
import pytest
import django
from django.conf import settings
from typing import Generator

# Add the backend directory to the Python path (before importing the backend
# `tests` package below, so it cannot resolve to the repo-root `tests/`).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.infrastructure.mock_influxdb import MockInfluxDBClient

# Without an MLflow server, MLflow's REST client retries a refused connection
# 7 times with exponential backoff (~5 minutes per call). Tests that reach
# http://localhost:5000 unmocked should fail fast instead. Export these
# variables to override (e.g. when running against a real MLflow server).
os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")

def pytest_configure():
    # Set test environment variables
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agentictrader.settings')
    os.environ.setdefault('DERIV_APP_ID', 'test_app_id')
    os.environ.setdefault('DERIV_API_ENDPOINT', 'wss://test.endpoint.com/websockets/v3')
    os.environ.setdefault('DERIV_RATE_LIMIT', '10')
    
    settings.DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
    settings.INSTALLED_APPS = [
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'trader',
    ]
    django.setup()

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "docker", "docker-compose.yml")

@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    return "test_agentictrader"

@pytest.fixture(scope="session")
def docker_services():
    """Mock docker services fixture when Docker is not available."""
    yield

@pytest.fixture(scope="session")
def influxdb_container(docker_services) -> Generator[str, None, None]:
    """Start influxdb container and wait for it to be ready."""
    # Check if InfluxDB is up and responding
    subprocess.run(["docker", "exec", "test_agentictrader-influxdb-1", "influx", "ping"], check=True)
    yield "8086"  # Return default InfluxDB port

@pytest.fixture(scope="session")
def influxdb_client():
    """Provide a mock InfluxDB client for testing."""
    client = MockInfluxDBClient(
        url="http://localhost:8086",
        token="mock-token",
        org="test-org"
    )
    return client
