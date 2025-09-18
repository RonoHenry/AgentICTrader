"""
Test script for live Deriv API connection.
"""
import asyncio
import logging
import os
import pytest
from datetime import datetime, UTC, timedelta

from trader.infrastructure.deriv_api import DerivAPIClient
from trader.infrastructure.market_data_types import TickHistoryRequest

@pytest.mark.asyncio
async def test_live_connection():
    # Get API token from environment variable for security
    api_token = os.getenv("DERIV_API_TOKEN")
    if not api_token:
        print("Please set DERIV_API_TOKEN environment variable")
        return

    # Set up logging
    logging.basicConfig(level=logging.DEBUG)
    
    print(f"\nAPI Token: {api_token}")
    print(f"App ID: 98247")
    
    # Create client with your app_id
    client = DerivAPIClient(app_id="98247")  # AgentICTrader159 app_id
    
    try:
        # Connect first
        print("\n1. Testing connection to Deriv API...")
        await client.connect()
        print("✓ Connection established")
        
        # Then authorize with the token
        print("\n2. Testing authorization...")
        auth_response = await client.authorize(token=api_token)
        print(f"✓ Authorized successfully as: {auth_response.get('email')}")
        print(f"  Account type: {auth_response.get('landing_company_name', 'unknown')}")
        print(f"  Currency: {auth_response.get('currency', 'unknown')}")
        print(f"  Balance: {auth_response.get('balance', 'unknown')}")
        
        # Test with different symbols
        symbols = ["R_100", "frxEURUSD", "frxGBPUSD"]
        
        for symbol in symbols:
            print(f"\n3. Testing tick history for {symbol}...")
            end_time = datetime.now(UTC)
            start_time = end_time - timedelta(minutes=1)  # Get just 1 minute of data for testing
            
            request = TickHistoryRequest(
                symbol=symbol,
                start=start_time,
                end=end_time,
                style="ticks"
            )
        
            try:
                response = await client.get_tick_history(request)
                print(f"✓ Received {len(response.ticks)} ticks")
                
                if response.ticks:
                    first_tick = response.ticks[0]
                    last_tick = response.ticks[-1]
                    print(f"  First tick: {first_tick.timestamp.strftime('%H:%M:%S.%f')} - Price: {first_tick.price}")
                    print(f"  Last tick:  {last_tick.timestamp.strftime('%H:%M:%S.%f')} - Price: {last_tick.price}")
                    
                    if len(response.ticks) > 1:
                        time_diff = (last_tick.timestamp - first_tick.timestamp).total_seconds()
                        price_change = float(last_tick.price - first_tick.price)
                        print(f"  Time span: {time_diff:.2f} seconds")
                        print(f"  Price change: {price_change:+.5f}")
                
            except Exception as e:
                print(f"✗ Error testing {symbol}: {str(e)}")
                
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
    finally:
        print("\n4. Closing connection...")
        await client.close()
        print("✓ Connection closed")

if __name__ == "__main__":
    asyncio.run(test_live_connection())
