import os
import pytest
import docker
import django
from django.conf import settings
from typing import Generator
import subprocess

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
