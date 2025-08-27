import os
import pytest
import docker
import django
from django.conf import settings
from typing import Generator
import subprocess

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
def docker_compose_file(pytestconfig):
    return os.path.join(str(pytestconfig.rootdir), "docker", "docker-compose.yml")

@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    return "test_agentictrader"

@pytest.fixture(scope="session")
def docker_services(docker_compose_file, docker_compose_project_name):
    """Start docker services defined in docker-compose.yml"""
    docker_compose_path = str(docker_compose_file)
    project_name = docker_compose_project_name
    
    # Start containers
    subprocess.run(["docker", "compose", "-f", docker_compose_path, "-p", project_name, "up", "-d"], check=True)
    
    yield
    
    # Stop containers
    subprocess.run(["docker", "compose", "-f", docker_compose_path, "-p", project_name, "down"], check=True)

@pytest.fixture(scope="session")
def influxdb_container(docker_services) -> Generator[str, None, None]:
    """Start influxdb container and wait for it to be ready."""
    # Check if InfluxDB is up and responding
    subprocess.run(["docker", "exec", "test_agentictrader-influxdb-1", "influx", "ping"], check=True)
    yield "8086"  # Return default InfluxDB port
