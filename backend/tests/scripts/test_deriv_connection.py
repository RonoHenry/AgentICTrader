"""
Test script for Deriv API connection.
"""
import asyncio
import os
import sys
import json
from datetime import datetime, timezone, timedelta

# Add backend directory to Python path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, backend_dir)

from trader.infrastructure.deriv_api import DerivAPIClient, DerivConfig
from trader.infrastructure.provider_config import RateLimitConfig
from trader.infrastructure.market_data_types import TickHistoryRequest

async def test_deriv_connection():
    """Test Deriv API connection and basic functionality."""
    print("Initializing Deriv API client...")
    
    # Create configuration
    config = DerivConfig(
        app_id="98843",  # Using your app ID
        api_token="iri7xZnwzvw0NfE",  # Your API token
        endpoint="wss://ws.binaryws.com/websockets/v3",
        rate_limit=RateLimitConfig(requests_per_second=2)
    )
    
    client = DerivAPIClient(config)
    
    try:
        # Connect and authorize
        print("Connecting to Deriv API...")
        await client.connect()
        print("Successfully connected!")
        
        # Get available symbols
        print("\nFetching available symbols...")
        symbols = await client.get_symbols()
        print(f"Found {len(symbols)} available symbols")
        
        # Get details for EURUSD
        print("\nFetching EURUSD details...")
        symbol_info = await client.get_symbol_info("frxEURUSD")
        if symbol_info:
            print("EURUSD Details:")
            print(json.dumps(symbol_info, indent=2))
        
        # Get historical data
        print("\nFetching historical data for EURUSD...")
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=5)
        
        request = TickHistoryRequest(
            symbol="frxEURUSD",
            start=start_time,
            end=end_time
        )
        
        history = await client.get_tick_history(request)
        print(f"Received {len(history.ticks)} ticks")
        print("\nLatest 5 ticks:")
        for tick in history.ticks[-5:]:
            print(f"Time: {tick.timestamp}, Price: {tick.price}")
        
        # Test real-time data
        print("\nSubscribing to EURUSD ticks...")
        async for tick in client.subscribe_ticks("frxEURUSD"):
            print(f"Real-time tick - Time: {tick.timestamp}, Price: {tick.price}")
            # Get 5 ticks and then break
            if len(history.ticks) >= 5:
                break
                
        print("\nUnsubscribing from EURUSD ticks...")
        await client.unsubscribe_ticks("frxEURUSD")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        print("\nClosing connection...")
        await client.disconnect()
        print("Connection closed")

if __name__ == "__main__":
    asyncio.run(test_deriv_connection())
