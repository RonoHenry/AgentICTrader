import pytest
from trader.models import Symbol

@pytest.mark.unit
def test_symbol_creation():
    """Test basic symbol creation"""
    symbol = Symbol(
        name="EUR/USD",
        description="Euro vs US Dollar"
    )
    assert symbol.name == "EUR/USD"
    assert symbol.description == "Euro vs US Dollar"
    assert symbol.is_active == True

@pytest.mark.unit
def test_symbol_string_representation():
    """Test symbol string representation"""
    symbol = Symbol(name="EUR/USD")
    assert str(symbol) == "EUR/USD"
