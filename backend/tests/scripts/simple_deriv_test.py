"""
Simple test script for Deriv API connection.
"""
import asyncio
import json
import ssl
import certifi
import websockets

async def test_connection():
    """Test connection to Deriv API."""
    try:
        # Create SSL context with system certificates
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # Connect to Deriv API
        print("Connecting to Deriv API...")
        async with websockets.connect(
            'wss://ws.binaryws.com/websockets/v3?app_id=98843',
            ssl=ssl_context
        ) as websocket:
            print("Connected!")
            
            # Authorize with token
            print("\nAuthorizing...")
            auth_request = {
                "authorize": "iri7xZnwzvw0NfE"
            }
            await websocket.send(json.dumps(auth_request))
            response = await websocket.recv()
            print(f"Authorization response: {response}")
            
            # Get available symbols
            print("\nGetting available symbols...")
            symbols_request = {
                "active_symbols": "brief",
                "product_type": "basic"
            }
            await websocket.send(json.dumps(symbols_request))
            response = json.loads(await websocket.recv())
            
            if "error" in response:
                print(f"Error: {response['error']['message']}")
            else:
                symbols = response.get("active_symbols", [])
                print(f"Found {len(symbols)} symbols")
                print("\nFirst 5 symbols:")
                for symbol in symbols[:5]:
                    print(f"- {symbol['symbol']}: {symbol['display_name']}")
                    
            # Get EURUSD ticks
            print("\nSubscribing to EURUSD ticks...")
            ticks_request = {
                "ticks": "frxEURUSD",
                "subscribe": 1
            }
            await websocket.send(json.dumps(ticks_request))
            
            # Get 5 ticks
            print("\nReceiving ticks:")
            for _ in range(5):
                tick = json.loads(await websocket.recv())
                if "tick" in tick:
                    print(f"Price: {tick['tick']['quote']}, Time: {tick['tick']['epoch']}")
                else:
                    print(f"Unexpected response: {tick}")
                    
            # Unsubscribe
            print("\nUnsubscribing...")
            unsub_request = {
                "forget_all": ["ticks"]
            }
            await websocket.send(json.dumps(unsub_request))
            response = await websocket.recv()
            print("Unsubscribed successfully")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    print("Starting Deriv API connection test...")
    asyncio.run(test_connection())
    print("\nTest complete!")
