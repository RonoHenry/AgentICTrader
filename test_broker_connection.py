import sys
import asyncio
sys.path.insert(0, 'backend')

from trader.infrastructure.deriv_api import DerivAPIClient

async def test_connection():
    """Test if we can connect to Deriv API and get real data"""
    client = DerivAPIClient(
        app_id='pat_584b6e331c13f95c36462d39b12f9473498040265120ce81bce2c186d8983909'
    )
    
    try:
        print("🔌 Connecting to Deriv API...")
        await client.connect()
        print("✅ Connected!")
        
        print("\n📊 Fetching available symbols...")
        symbols = await client.get_symbols()
        print(f"✅ Found {len(symbols)} trading symbols")
        
        # Show sample symbols
        print("\n📋 Sample symbols:")
        for symbol in symbols[:10]:
            print(f"  - {symbol.get('symbol', 'N/A')}: {symbol.get('display_name', 'N/A')}")
        
        # Try to get real OHLC data for EURUSD
        print("\n📈 Fetching real OHLC data for frxEURUSD (last 10 candles)...")
        candles = await client.get_ohlc(symbol='frxEURUSD', interval=60, count=10)
        print(f"✅ Received {len(candles)} candles")
        
        if candles:
            latest = candles[-1]
            print(f"\n🕐 Latest candle:")
            print(f"  Time: {latest.get('epoch', 'N/A')}")
            print(f"  Open: {latest.get('open', 'N/A')}")
            print(f"  High: {latest.get('high', 'N/A')}")
            print(f"  Low: {latest.get('low', 'N/A')}")
            print(f"  Close: {latest.get('close', 'N/A')}")
        
        print("\n✅ SUCCESS: Broker API is working and returning real data!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")

if __name__ == "__main__":
    asyncio.run(test_connection())
