"""Docker container setup for tests."""
import os
import time
import docker
import pytest
import logging
from typing import Generator

logger = logging.getLogger(__name__)

class DockerSetup:
    """Manage Docker containers for testing."""
    
    def __init__(self):
        """Initialize Docker client."""
        self.client = docker.from_env()
        self.containers = {}
    
    def start_influxdb(self) -> None:
        """Start InfluxDB container."""
        try:
            # Remove any existing container
            try:
                container = self.client.containers.get('influxdb-test')
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
            
            # Start new container
            container = self.client.containers.run(
                'influxdb:2.7',
                name='influxdb-test',
                detach=True,
                environment={
                    'DOCKER_INFLUXDB_INIT_MODE': 'setup',
                    'DOCKER_INFLUXDB_INIT_USERNAME': 'admin',
                    'DOCKER_INFLUXDB_INIT_PASSWORD': 'adminadmin',
                    'DOCKER_INFLUXDB_INIT_ORG': 'agentic',
                    'DOCKER_INFLUXDB_INIT_BUCKET': 'market_data',
                    'DOCKER_INFLUXDB_INIT_ADMIN_TOKEN': 'test-token'
                },
                ports={'8086/tcp': 8086},
                remove=True
            )
            
            self.containers['influxdb'] = container
            
            # Wait for container to be ready
            time.sleep(5)  # Give InfluxDB time to initialize
            
            logger.info("InfluxDB container started")
            
        except Exception as e:
            logger.error(f"Failed to start InfluxDB container: {e}")
            raise
    
    def stop_all(self) -> None:
        """Stop all test containers."""
        for name, container in self.containers.items():
            try:
                container.stop()
                logger.info(f"Stopped {name} container")
            except Exception as e:
                logger.warning(f"Error stopping {name} container: {e}")

@pytest.fixture(scope="session")
def docker_setup() -> Generator[DockerSetup, None, None]:
    """Provide Docker setup for tests."""
    setup = DockerSetup()
    try:
        setup.start_influxdb()
        yield setup
    finally:
        setup.stop_all()
