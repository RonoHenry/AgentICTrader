"""
Test core project setup and infrastructure.
"""
import pytest
from django.conf import settings
from django.db import connections
from django.core.cache import cache
import redis
import psycopg2
from influxdb_client import InfluxDBClient

def test_django_configuration():
    """Test that Django is configured correctly."""
    assert settings.INSTALLED_APPS is not None
    assert 'trader' in settings.INSTALLED_APPS
    assert 'users' in settings.INSTALLED_APPS
    assert 'social' in settings.INSTALLED_APPS

@pytest.mark.django_db
def test_database_connection():
    """Test database connections."""
    # Test default (PostgreSQL) connection
    connection = connections['default']
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1

def test_redis_connection():
    """Test Redis connection."""
    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=int(settings.REDIS_PORT),
            db=0
        )
        r.ping()
        assert True
    except redis.ConnectionError:
        pytest.fail("Could not connect to Redis")

def test_influxdb_connection():
    """Test InfluxDB connection."""
    try:
        client = InfluxDBClient(
            url=f"http://{settings.DATABASES['timeseries']['HOST']}:{settings.DATABASES['timeseries']['PORT']}",
            token=settings.DATABASES['timeseries']['TOKEN'],
            org="agentic"
        )
        health = client.health()
        assert health.status == "pass"
    except Exception as e:
        pytest.fail(f"Could not connect to InfluxDB: {str(e)}")

def test_docker_environment():
    """Test Docker environment variables."""
    assert settings.DATABASES['default']['HOST'] is not None
    assert settings.DATABASES['timeseries']['HOST'] is not None
    assert settings.REDIS_HOST is not None
