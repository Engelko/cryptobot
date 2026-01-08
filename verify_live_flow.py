import asyncio
from antigravity.logging import configure_logging, get_logger
from antigravity.event import event_bus, KlineEvent, on_event
from antigravity.websocket_client import BybitWebSocket
from antigravity.config import settings

logger = get_logger("debug_flow")

@on_event(KlineEvent)
async def on_kline(event: KlineEvent):
    print(f"✅ KLINE RECEIVED: {event.symbol} Close={event.close} Confirmed=True")

async def main():
    configure_logging()
    print("🚀 Starting Diagnostic Tool...")
    print(f"Monitoring Symbols: {settings.TRADING_SYMBOLS}")

    # Start Event Bus
    event_bus.start()

    # Start WebSocket
    ws = BybitWebSocket()
    topics = [f"kline.1.{s}" for s in settings.TRADING_SYMBOLS]
    print(f"Connecting to WS: {ws.url}")
    print(f"Subscribing to: {topics}")

    await ws.connect(topics)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
