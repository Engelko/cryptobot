import asyncio
import time
from antigravity.engine import strategy_engine
from antigravity.event import event_bus, KlineEvent
from antigravity.logging import configure_logging
from antigravity.strategies.rsi import RSIStrategy

async def main():
    configure_logging()
    
    rsi_strategy = RSIStrategy(name="RSI_Bot", symbols=["BTCUSDT"], period=14, overbought=70, oversold=30)
    rsi_strategy.start()
    strategy_engine.register_strategy(rsi_strategy)
    
    event_bus.start()
    await strategy_engine.start()
    
    print("X-Testing RSI Strategy (Extended Data)...")
    
    # Generate 50 candles
    base_price = 50000.0
    for i in range(50):
        price = base_price + (i * 100)
        # Spike at the end
        if i >= 45:
             price = base_price + (i * 800) 
             
        event = KlineEvent(
            symbol="BTCUSDT",
            interval="1",
            open=price, close=price, high=price, low=price, volume=100,
            timestamp=int(time.time() * 1000) + (i * 60000)
        )
        await event_bus.publish(event)
        # Yield to event bus
        await asyncio.sleep(0.05)
    
    # Allow processing time
    await asyncio.sleep(2)
    
    await strategy_engine.stop()
    await event_bus.stop()
    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
