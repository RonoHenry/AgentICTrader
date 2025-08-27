"""
Test trader models and database schema.
"""
import pytest
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from trader.models import Symbol, Trade, PO3Formation
from django.utils import timezone
from django.core.exceptions import ValidationError

@pytest.mark.django_db
class TestTraderModels(TestCase):
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testtrader',
            password='testpass123'
        )
        self.symbol = Symbol.objects.create(
            name="EUR/USD",
            description="Euro/US Dollar pair",
            is_active=True
        )
        self.po3_formation = PO3Formation.objects.create(
            symbol=self.symbol,
            timeframe='H1',
            phase='accumulation',
            start_time=timezone.now(),
            end_time=timezone.now(),
            start_price=Decimal('1.2000'),
            end_price=Decimal('1.2100'),
            confidence=0.85
        )
        
    def test_symbol_creation(self):
        """Test that we can create a Symbol."""
        assert self.symbol.name == "EUR/USD"
        assert self.symbol.description == "Euro/US Dollar pair"
        assert self.symbol.is_active is True
        
    def test_po3_formation_creation(self):
        """Test that we can create a PO3Formation."""
        assert self.po3_formation.symbol == self.symbol
        assert self.po3_formation.phase == 'accumulation'
        assert self.po3_formation.confidence == 0.85
        
    def test_trade_creation(self):
        """Test that we can create a Trade."""
        trade = Trade.objects.create(
            user=self.user,
            symbol=self.symbol,
            po3_formation=self.po3_formation,
            trade_type='long',
            status='open',
            entry_price=Decimal('1.2000'),
            stop_loss=Decimal('1.1950'),
            take_profit=Decimal('1.2100'),
            position_size=Decimal('1.0')
        )
        assert trade.symbol == self.symbol
        assert trade.trade_type == 'long'
        assert trade.status == 'open'
        assert trade.entry_price == Decimal('1.2000')
        
    def test_trade_lifecycle(self):
        """Test the complete lifecycle of a trade."""
        # Create trade
        trade = Trade.objects.create(
            user=self.user,
            symbol=self.symbol,
            po3_formation=self.po3_formation,
            trade_type='long',
            status='pending',
            entry_price=Decimal('1.2000'),
            stop_loss=Decimal('1.1950'),
            take_profit=Decimal('1.2100'),
            position_size=Decimal('1.0')
        )
        
        # Update to open
        trade.status = 'open'
        trade.save()
        assert trade.status == 'open'
        
        # Close trade with profit
        trade.status = 'closed'
        trade.pnl = Decimal('100.00')
        trade.closed_at = timezone.now()
        trade.save()
        
        assert trade.status == 'closed'
        assert trade.pnl == Decimal('100.00')
        assert trade.closed_at is not None
