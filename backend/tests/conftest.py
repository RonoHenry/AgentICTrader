"""
Base test configuration for AgentICTrader.
"""
import os
import sys
import django
import pytest
from django.conf import settings

# Get the absolute path to the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def pytest_configure():
    """Configure Django for testing."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agentictrader.settings_test')
    django.setup()

def get_user_model():
    """Get User model after Django is configured."""
    from django.contrib.auth.models import User
    return User

def pytest_collection_modifyitems(config, items):
    """Modify test collection to mark infrastructure tests as such."""
    for item in items:
        if "test_infrastructure" in str(item.fspath):
            item.add_marker(pytest.mark.infrastructure)

@pytest.fixture
def test_user():
    """Create a test user."""
    User = get_user_model()
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
