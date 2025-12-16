import asyncio
import time
from antigravity.event import event_bus, KlineEvent, SentimentEvent, on_event
from antigravity.copilot import AICopilot
from antigravity.logging import configure_logging

@on_event(SentimentEvent)
async def handle_sentiment(event: SentimentEvent):
    print(f"X-Sentiment Received: Score={event.score} | Reason={event.reasoning[:50]}...")

async def main():
    configure_logging()
    
    # Init Copilot
    copilot = AICopilot()
    await copilot.start()
    
    event_bus.start()
    
    print("X-Testing AI Copilot...")
    print(">> Sending 5 Candles (Uptrend)...")
    
    # Provide 5 candles to trigger analysis (min data = 5)
    base_price = 50000.0
    for i in range(1, 6):
        price = base_price + (i * 100)
        event = KlineEvent(
            symbol="BTCUSDT",
            interval="1",
            open=price, close=price, high=price, low=price, volume=100,
            timestamp=int(time.time() * 1000)
        )
        await event_bus.publish(event)
        await asyncio.sleep(0.1)

    # Wait for async AI call (Mocked in absence of Key, or Real if Key exists)
    # The Log warning in ai.py handles no-key scenario gracefullly
    print(">> Waiting for Analysis...")
    await asyncio.sleep(3)
    
    await copilot.stop()
    await event_bus.stop()
    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
