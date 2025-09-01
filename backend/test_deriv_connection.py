import asyncio
import websockets

async def test_connection():
    try:
        uri = "wss://ws.binaryws.com/websockets/v3"
        async with websockets.connect(uri) as websocket:
            print("Connected successfully!")
            
            # Send authorize request with app_id
            auth_request = {
                "app_id": "98247",  # Using the app_id from test_deriv_live.py
                "authorize": "1234"  # Dummy token for testing
            }
            
            await websocket.send(json.dumps(auth_request))
            response = await websocket.recv()
            print(f"Response: {response}")
    except Exception as e:
        print(f"Connection failed: {e}")

# Add json import
import json
asyncio.run(test_connection())
