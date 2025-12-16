import asyncio
from typing import Optional
from antigravity.strategy import AbstractStrategy, Signal, SignalType
from antigravity.engine import strategy_engine
from antigravity.event import event_bus, MarketDataEvent
from antigravity.logging import configure_logging

class RiskyStrategy(AbstractStrategy):
    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if event.topic == "safe":
             return Signal(SignalType.BUY, "BTCUSDT", 50000.0, reason="Safe Trade")
        
        if event.topic == "blocked":
            return Signal(SignalType.BUY, "BTCUSDT", 50000.0, reason="Blocked Trade")
        return None

async def main():
    configure_logging()
    
    # 1. Setup Engine & Strategy
    risky = RiskyStrategy(name="RiskyBot", symbols=["BTCUSDT"])
    risky.start()
    strategy_engine.register_strategy(risky)
    
    # 2. Start Engine & Event Bus
    event_bus.start()
    await strategy_engine.start()
    
    print("X-Testing Risk Manager...")
    
    # Case 1: Normal Signal (Should be accepted)
    print(">> Sending Safe Signal")
    await event_bus.publish(MarketDataEvent(topic="safe", data={}))
    await asyncio.sleep(0.5)
    
    # Case 2: Daily Loss Limit Hit (Simulate)
    print(">> Simulating Max Loss")
    strategy_engine.risk_manager.current_daily_loss = 200.0 # Limit is 100.0
    await event_bus.publish(MarketDataEvent(topic="blocked", data={}))
    await asyncio.sleep(0.5)
    
    await strategy_engine.stop()
    await event_bus.stop()
    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
