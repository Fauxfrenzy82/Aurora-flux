import asyncio
from brokers.deriv_client import deriv

async def test():
    await deriv.connect()
    
    symbols = ['R_100', 'R_50', 'frxEURUSD', 'EURUSD', '1HZ100V']
    
    for symbol in symbols:
        candles = await deriv.get_candles(symbol, '1h', 5)
        print(f'{symbol}: {len(candles)} candles')

asyncio.run(test())