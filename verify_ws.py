import asyncio
import aiohttp
import json
import time
from antigravity.config import settings

async def verify_ws():
    url = "wss://stream-testnet.bybit.com/v5/public/linear" if settings.BYBIT_TESTNET else "wss://stream.bybit.com/v5/public/linear"
    print(f"Connecting to {url}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.ws_connect(url) as ws:
                print("✓ Connected to WebSocket")

                # Subscribe to BTCUSDT klines
                subscribe_msg = {
                    "op": "subscribe",
                    "args": ["kline.1.BTCUSDT"]
                }
                await ws.send_json(subscribe_msg)
                print("✓ Sent subscription request for BTCUSDT")

                start_time = time.time()
                received_kline = False

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if "topic" in data and "kline" in data["topic"]:
                            print(f"✓ Received kline for {data['topic']}")
                            received_kline = True
                            break
                        elif "success" in data:
                            print(f"✓ Subscription response: {data}")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"✗ WebSocket error: {ws.exception()}")
                        break

                    if time.time() - start_time > 15:
                        print("✗ Timeout waiting for kline data")
                        break

                if received_kline:
                    print("✓ WebSocket Health Check Passed")
                else:
                    print("✗ WebSocket Health Check Failed (No data received)")

    except Exception as e:
        print(f"✗ Connection failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(verify_ws())
