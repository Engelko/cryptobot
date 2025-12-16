import asyncio
from typing import Optional
from antigravity.strategy import AbstractStrategy, Signal, SignalType
from antigravity.engine import strategy_engine
from antigravity.event import event_bus, MarketDataEvent
from antigravity.logging import configure_logging

class DummyStrategy(AbstractStrategy):
    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if event.topic == "test_topic":
            return Signal(
                type=SignalType.BUY,
                symbol="BTCUSDT",
                price=50000.0,
                reason="Test Signal"
            )
        return None

async def main():
    configure_logging()
    
    # 1. Setup Engine & Strategy
    dummy = DummyStrategy(name="DummyV1", symbols=["BTCUSDT"])
    dummy.start()
    strategy_engine.register_strategy(dummy)
    
    # 2. Start Engine & Event Bus
    event_bus.start()
    await strategy_engine.start()
    
    print("X-Testing Engine...")
    
    # 3. Publish Test Event
    await event_bus.publish(MarketDataEvent(topic="test_topic", data={"price": 50000}))
    
    # Allow processing time
    await asyncio.sleep(1)
    
    await strategy_engine.stop()
    await event_bus.stop()
    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
