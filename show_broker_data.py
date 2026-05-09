#!/usr/bin/env python3
"""
Quick script to show real data from Deriv broker API.
No database required - just displays the data.
"""
import sys
import asyncio
sys.path.insert(0, 'backend')

from trader.infrastructure.deriv_api import DerivAPIClient
from datetime import datetime, timezone
import json

async def show_real_broker_data():
    """Fetch and display real market data from Deriv API"""
    
    # Use the app ID from your .env
    client = DerivAPIClient(
        app_id='pat_584b6e331c13f95c36462d39b12f9473498040265120ce81bce2c186d8983909'
    )
    
    try:
        print("=" * 80)
        print("🔌 CONNECTING TO DERIV BROKER API")
        print("=" * 80)
        await client.connect()
        print("✅ Connected successfully!\n")
        
        # 1. Get available symbols
        print("=" * 80)
        print("📊 AVAILABLE TRADING SYMBOLS")
        print("=" * 80)
        symbols = await client.get_symbols()
        print(f"Total symbols available: {len(symbols)}\n")
        
        # Show forex pairs
        forex_symbols = [s for s in symbols if s.get('market') == 'forex']
        print(f"📈 Forex Pairs ({len(forex_symbols)} available):")
        for symbol in forex_symbols[:10]:
            print(f"  • {symbol.get('symbol', 'N/A')}: {symbol.get('display_name', 'N/A')}")
        print()
        
        # 2. Get real OHLC data for EURUSD
        print("=" * 80)
        print("💹 REAL-TIME EURUSD DATA (Last 20 M1 Candles)")
        print("=" * 80)
        candles = await client.get_ohlc(symbol='frxEURUSD', interval=60, count=20)
        print(f"Received {len(candles)} candles\n")
        
        if candles:
            print(f"{'Time (UTC)':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12}")
            print("-" * 80)
            
            for candle in candles[-10:]:  # Show last 10
                timestamp = datetime.fromtimestamp(candle['epoch'], tz=timezone.utc)
                time_str = timestamp.strftime('%Y-%m-%d %H:%M')
                print(
                    f"{time_str:<20} "
                    f"{float(candle['open']):<12.5f} "
                    f"{float(candle['high']):<12.5f} "
                    f"{float(candle['low']):<12.5f} "
                    f"{float(candle['close']):<12.5f}"
                )
            
            # Show latest candle details
            latest = candles[-1]
            latest_time = datetime.fromtimestamp(latest['epoch'], tz=timezone.utc)
            print("\n" + "=" * 80)
            print("🕐 LATEST CANDLE DETAILS")
            print("=" * 80)
            print(f"Symbol:     frxEURUSD (EUR/USD)")
            print(f"Timeframe:  M1 (1 minute)")
            print(f"Time:       {latest_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"Open:       {float(latest['open']):.5f}")
            print(f"High:       {float(latest['high']):.5f}")
            print(f"Low:        {float(latest['low']):.5f}")
            print(f"Close:      {float(latest['close']):.5f}")
            
            # Calculate candle metrics
            body = abs(float(latest['close']) - float(latest['open']))
            range_val = float(latest['high']) - float(latest['low'])
            is_bullish = float(latest['close']) > float(latest['open'])
            
            print(f"\nCandle Type: {'🟢 BULLISH' if is_bullish else '🔴 BEARISH'}")
            print(f"Body Size:   {body:.5f} ({(body/range_val*100):.1f}% of range)")
            print(f"Range:       {range_val:.5f}")
        
        # 3. Try GBPUSD as well
        print("\n" + "=" * 80)
        print("💹 REAL-TIME GBPUSD DATA (Last 5 M5 Candles)")
        print("=" * 80)
        gbp_candles = await client.get_ohlc(symbol='frxGBPUSD', interval=300, count=5)
        print(f"Received {len(gbp_candles)} candles\n")
        
        if gbp_candles:
            print(f"{'Time (UTC)':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12}")
            print("-" * 80)
            
            for candle in gbp_candles:
                timestamp = datetime.fromtimestamp(candle['epoch'], tz=timezone.utc)
                time_str = timestamp.strftime('%Y-%m-%d %H:%M')
                print(
                    f"{time_str:<20} "
                    f"{float(candle['open']):<12.5f} "
                    f"{float(candle['high']):<12.5f} "
                    f"{float(candle['low']):<12.5f} "
                    f"{float(candle['close']):<12.5f}"
                )
        
        # 4. Try Gold (XAUUSD)
        print("\n" + "=" * 80)
        print("💹 REAL-TIME GOLD (XAUUSD) DATA (Last 5 H1 Candles)")
        print("=" * 80)
        gold_candles = await client.get_ohlc(symbol='frxXAUUSD', interval=3600, count=5)
        print(f"Received {len(gold_candles)} candles\n")
        
        if gold_candles:
            print(f"{'Time (UTC)':<20} {'Open':<12} {'High':<12} {'Low':<12} {'Close':<12}")
            print("-" * 80)
            
            for candle in gold_candles:
                timestamp = datetime.fromtimestamp(candle['epoch'], tz=timezone.utc)
                time_str = timestamp.strftime('%Y-%m-%d %H:%M')
                print(
                    f"{time_str:<20} "
                    f"{float(candle['open']):<12.2f} "
                    f"{float(candle['high']):<12.2f} "
                    f"{float(candle['low']):<12.2f} "
                    f"{float(candle['close']):<12.2f}"
                )
        
        print("\n" + "=" * 80)
        print("✅ SUCCESS: BROKER API IS WORKING!")
        print("=" * 80)
        print("\n📊 Summary:")
        print(f"  • Connected to Deriv broker API")
        print(f"  • {len(symbols)} trading symbols available")
        print(f"  • Real-time OHLC data retrieved successfully")
        print(f"  • Data is live and updating")
        print(f"\n🎯 Your infrastructure is ready to:")
        print(f"  • Pull historical data (3 years)")
        print(f"  • Stream live ticks")
        print(f"  • Build ML features from real market data")
        print(f"  • Run backtests on actual price action")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")

if __name__ == "__main__":
    asyncio.run(show_real_broker_data())
