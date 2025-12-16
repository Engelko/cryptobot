import asyncio
from antigravity.client import BybitClient
from antigravity.logging import configure_logging

async def main():
    configure_logging()
    client = BybitClient()
    try:
        print("Fetching Server Time...")
        t = await client.get_server_time()
        print(f"X-Server Time: {t}")
        
        print("Fetching BTCUSDT Kline...")
        kline = await client.get_kline("BTCUSDT", "1", 5)
        print(f"X-Kline Count: {len(kline)}")
        if kline:
             print(f"X-Last Candle: {kline[0]}")
        
    except Exception as e:
        print(f"X-ERROR: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
