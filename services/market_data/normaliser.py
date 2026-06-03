"""
Re-export of the tick normaliser from services/market-data/normaliser.py.

Python cannot import from directories with hyphens, so this module
provides a clean import path: `from services.market_data.normaliser import ...`
"""
import importlib
import sys
import os

# Dynamically load the module from the hyphenated directory
_market_data_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),  # services/
    "market-data",
    "normaliser.py",
)

import importlib.util as _util
_spec = _util.spec_from_file_location("services._market_data_normaliser", _market_data_path)
_mod = _util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export public symbols
Candle = _mod.Candle
TickNormaliser = _mod.TickNormaliser
SUPPORTED_TIMEFRAMES = _mod.SUPPORTED_TIMEFRAMES
TIMEFRAME_SECONDS = _mod.TIMEFRAME_SECONDS

__all__ = [
    "Candle",
    "TickNormaliser",
    "SUPPORTED_TIMEFRAMES",
    "TIMEFRAME_SECONDS",
]
