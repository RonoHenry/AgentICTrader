"""
services.market_data — Python-importable alias for services/market-data.

Python cannot import from directories with hyphens in their names.
This package re-exports everything from the actual market-data service
modules so that test files can use `from services.market_data.xxx import yyy`.
"""
