import os
import sys
import pytest
import django
from django.conf import settings
from typing import Generator
from tests.infrastructure.mock_influxdb import MockInfluxDBClient

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def pytest_configure():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agentictrader.settings')
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
def influxdb_client():
    """Provide a mock InfluxDB client for testing."""
    client = MockInfluxDBClient(
        url="http://localhost:8086",
        token="mock-token",
        org="test-org"
    )
    return client
