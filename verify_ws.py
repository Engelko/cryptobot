import asyncio
from antigravity.websocket_client import BybitWebSocket
from antigravity.event import event_bus, MarketDataEvent, on_event
from antigravity.logging import configure_logging

received_count = 0

@on_event(MarketDataEvent)
async def handle_market_data(event: MarketDataEvent):
    global received_count
    print(f"X-WS Update: {event.topic} | Data Size: {len(str(event.data))}")
    received_count += 1

async def main():
    configure_logging()
    event_bus.start()
    
    ws = BybitWebSocket()
    # Subscribe to BTCUSDT Orderbook depth 1
    task = asyncio.create_task(ws.connect(["orderbook.1.BTCUSDT"]))
    
    print("Connecting to WS...")
    # Run for 10 seconds or until 5 messages
    for _ in range(10):
        await asyncio.sleep(1)
        if received_count >= 5:
            break
            
    await ws.close()
    await event_bus.stop()
    task.cancel()
    print(f"X-Test Complete. Received: {received_count}")

if __name__ == "__main__":
    asyncio.run(main())
