from influxdb_client import Point
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

class CandlePoint:
    def __init__(self, symbol: str, timeframe: str, timestamp: datetime, 
                 open: Decimal, high: Decimal, low: Decimal, close: Decimal, 
                 volume: int):
        # Validate inputs
        if not symbol:
            raise ValueError("Symbol cannot be empty")
        if not timeframe:
            raise ValueError("Timeframe cannot be empty")
        if high < low:
            raise ValueError("High price cannot be less than low price")
        if any(not isinstance(price, Decimal) for price in [open, high, low, close]):
            raise ValueError("Price values must be Decimal type")
        if not isinstance(volume, int):
            raise ValueError("Volume must be an integer")
        
        self.point = Point("candles")\
            .tag("symbol", symbol)\
            .tag("timeframe", timeframe)\
            .field("open", float(open))\
            .field("high", float(high))\
            .field("low", float(low))\
            .field("close", float(close))\
            .field("volume", volume)\
            .time(timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measurement": self.point._name,
            "tags": self.point._tags,
            "fields": self.point._fields,
            "time": self.point._time
        }

class PDArrayPoint:
    VALID_ZONE_TYPES = ["demand", "supply"]
    
    def __init__(self, symbol: str, timeframe: str, timestamp: datetime,
                 zone_type: str, high: Decimal, low: Decimal, strength: Decimal):
        # Validate inputs
        if zone_type not in self.VALID_ZONE_TYPES:
            raise ValueError(f"Zone type must be one of {self.VALID_ZONE_TYPES}")
        if not (0 <= float(strength) <= 1):
            raise ValueError("Strength must be between 0 and 1")
        if high < low:
            raise ValueError("High price cannot be less than low price")
        if any(not isinstance(price, Decimal) for price in [high, low, strength]):
            raise ValueError("Price and strength values must be Decimal type")
            
        self.point = Point("pd_arrays")\
            .tag("symbol", symbol)\
            .tag("timeframe", timeframe)\
            .tag("zone_type", zone_type)\
            .field("high", float(high))\
            .field("low", float(low))\
            .field("strength", float(strength))\
            .time(timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measurement": self.point._name,
            "tags": self.point._tags,
            "fields": self.point._fields,
            "time": self.point._time
        }
