import asyncio
from antigravity.engine import strategy_engine
from antigravity.event import event_bus, KlineEvent, MarketDataEvent
from antigravity.strategies.config import TrendConfig
from antigravity.strategies.trend import TrendFollowingStrategy

# Mock Data
async def inject_mock_data():
    print("Injecting Mock Data...")
    symbol = "BTCUSDT"

    # 1. Warmup / Init
    # We skip engine warmup for this test and just inject events

    # 2. Inject Sequence that causes Golden Cross
    # Slow SMA (200) is flat. Fast SMA (50) crosses up.

    # Simpler: Just print if strategy receives it.
    for i in range(5):
        print(f"Injecting Kline {i}")
        event = KlineEvent(
            symbol=symbol, interval="1",
            open=100, high=110, low=90, close=100 + i, volume=1000,
            timestamp=i*60000
        )
        await event_bus.publish(event)
        await asyncio.sleep(0.1)

async def main():
    # Setup
    config = TrendConfig(enabled=True, name="TrendMock", fast_period=2, slow_period=5) # fast periods for test
    strategy = TrendFollowingStrategy(config, ["BTCUSDT"])

    strategy_engine.register_strategy(strategy)
    await strategy_engine.start()

    # Run
    await inject_mock_data()

    await strategy_engine.stop()

if __name__ == "__main__":
    from antigravity.logging import configure_logging
    configure_logging()
    asyncio.run(main())
