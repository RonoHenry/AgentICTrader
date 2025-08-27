#!/bin/bash
set -e  # Exit on error

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if Docker container is running
docker_container_running() {
    docker ps --filter "name=$1" --format '{{.Names}}' | grep -q "^$1$"
}

# Check if Docker is installed and running
if ! command_exists docker; then
    echo "Error: Docker is not installed." >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker is not running." >&2
    exit 1
fi

# Ensure test services are running
echo "Ensuring test services are running..."
docker compose -f docker/docker-compose.test.yml up -d

# Wait for services to be ready
max_wait=30
waited=0
while [ $waited -lt $max_wait ]; do
    if docker ps --filter "name=agentictrader_influxdb" --format "{{.Status}}" | grep -q "Up"; then
        break
    fi
    echo "Waiting for services to be ready..."
    sleep 1
    waited=$((waited + 1))
done

if [ $waited -eq $max_wait ]; then
    echo "Error: Timeout waiting for services to be ready" >&2
    exit 1
fi

# Set environment variables
export PYTHONPATH="$(pwd)/backend:$PYTHONPATH"
export DJANGO_SETTINGS_MODULE="agentictrader.settings_test"

echo "Activating virtual environment..."
source ./agentic.venv/bin/activate || {
    echo "Error: Failed to activate virtual environment" >&2
    exit 1
}

# Run tests with coverage
echo "Running tests..."
if ! python -c "import pytest_cov" 2>/dev/null; then
    echo "Installing pytest-cov for coverage reporting..."
    pip install pytest-cov
fi

# Run tests with coverage
pytest --cov=backend --cov-report=term-missing "$@"
exit_code=$?

if [ $exit_code -ne 0 ]; then
    echo "Tests failed with exit code $exit_code" >&2
    exit $exit_code
fi

echo -e "\033[0;32mTests completed successfully!\033[0m"
