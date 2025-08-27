import pytest
from pathlib import Path
import sys
import os
import django
from django.conf import settings

# Add project root and backend to Python path
project_root = Path(__file__).parent.parent
backend_path = project_root / 'backend'
sys.path.append(str(project_root))
sys.path.append(str(backend_path))

def pytest_configure():
    """Configure Django for testing"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.agentictrader.settings')
    django.setup()

# Fixtures for Deriv API testing
@pytest.fixture
def mock_deriv_client():
    """Mock Deriv API client for testing"""
    class MockDerivClient:
        async def connect(self):
            return True
            
        async def authenticate(self):
            return {"authorize": "success"}
            
        async def get_market_data(self, symbol):
            return {
                "tick": {
                    "symbol": symbol,
                    "quote": 100.00,
                    "time": "2025-08-25 10:00:00"
                }
            }
    
    return MockDerivClient()

# Fixtures for market data
@pytest.fixture
def sample_candle_data():
    """Sample OHLC data for testing"""
    return {
        "timestamp": "2025-08-25 10:00:00",
        "open": 100.00,
        "high": 101.00,
        "low": 99.00,
        "close": 100.50,
        "volume": 1000
    }

# Fixtures for PDArray testing
@pytest.fixture
def sample_pd_array():
    """Sample Premium/Discount array data"""
    return {
        "premium_zones": [(101.00, 102.00), (103.00, 104.00)],
        "discount_zones": [(98.00, 99.00), (97.00, 98.00)]
    }
