"""
Base test configuration for AgentICTrader.
"""
import os
import sys
import pytest
from django.contrib.auth.models import User

# Get the absolute path to the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def pytest_collection_modifyitems(config, items):
    """Modify test collection to mark infrastructure tests as such."""
    for item in items:
        if "test_infrastructure" in str(item.fspath):
            item.add_marker(pytest.mark.infrastructure)

@pytest.fixture
def test_user():
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
