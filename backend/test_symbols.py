import asyncio
from brokers.deriv_client import deriv

async def test():
    await deriv.connect()
    print(f"Connected: {deriv.connected}")
    
    candles = await deriv.get_candles('R_100', '1h', 5)
    print(f"R_100 candles: {len(candles)}")
    
    if candles:
        print(f"First close: {candles[0]['close']}")
    else:
        print("NO CANDLE DATA")

asyncio.run(test())