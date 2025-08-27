from django.db import models
from django.contrib.auth.models import User

class Symbol(models.Model):
    name = models.CharField(max_length=20)
    description = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PO3Formation(models.Model):
    PHASE_CHOICES = [
        ('accumulation', 'Accumulation'),
        ('manipulation', 'Manipulation'),
        ('distribution', 'Distribution'),
    ]

    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)
    timeframe = models.CharField(max_length=10)
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    start_price = models.DecimalField(max_digits=10, decimal_places=5)
    end_price = models.DecimalField(max_digits=10, decimal_places=5)
    confidence = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['symbol', 'timeframe', 'start_time']),
        ]

class Trade(models.Model):
    TRADE_TYPE_CHOICES = [
        ('long', 'Long'),
        ('short', 'Short'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE)
    po3_formation = models.ForeignKey(PO3Formation, on_delete=models.SET_NULL, null=True)
    trade_type = models.CharField(max_length=10, choices=TRADE_TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    entry_price = models.DecimalField(max_digits=10, decimal_places=5)
    stop_loss = models.DecimalField(max_digits=10, decimal_places=5)
    take_profit = models.DecimalField(max_digits=10, decimal_places=5)
    position_size = models.DecimalField(max_digits=10, decimal_places=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True)
    pnl = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'symbol', 'created_at']),
            models.Index(fields=['status', 'created_at']),
        ]
