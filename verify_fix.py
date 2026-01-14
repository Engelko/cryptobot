import asyncio
import time
import os
import yaml
from antigravity.engine import strategy_engine
from antigravity.event import event_bus, KlineEvent
from antigravity.logging import configure_logging, get_logger
from antigravity.strategies.config import load_strategy_config

# Import the Improved Strategies exactly as main.py does
from antigravity.strategies.trend_improved import GoldenCrossImproved as TrendFollowingStrategy
from antigravity.strategies.mean_reversion_improved import BollingerRSIImproved as MeanReversionStrategy
from antigravity.strategies.grid_improved import GridMasterImproved as GridStrategy

# Mock Settings for test
class MockSettings:
    TRADING_SYMBOLS = ["BTCUSDT"]

logger = get_logger("verify_fix")

async def main():
    configure_logging()

    # 1. Load Strategy Config
    config = load_strategy_config("strategies.yaml")
    symbols = MockSettings.TRADING_SYMBOLS

    print(f"Loaded Config: {config}")

    # 2. Register Strategies (Trend and Mean Reversion)
    # Using the same syntax as main.py

    if config.trend_following:
        # Force Enable for Test
        config.trend_following.enabled = True
        strategy_engine.register_strategy(TrendFollowingStrategy(config.trend_following, symbols))
        print("Registered: TrendFollowing (Improved)")

    if config.mean_reversion:
        config.mean_reversion.enabled = True
        strategy_engine.register_strategy(MeanReversionStrategy(config.mean_reversion, symbols))
        print("Registered: MeanReversion (Improved)")

    if config.grid:
        config.grid.enabled = True
        # Ensure grid params allow initialization
        config.grid.lower_price = 45000.0
        config.grid.upper_price = 55000.0
        strategy_engine.register_strategy(GridStrategy(config.grid, symbols))
        print("Registered: Grid (Improved)")

    event_bus.start()
    await strategy_engine.start()

    print("--- Starting Data Injection ---")

    base_price = 50000.0

    # Inject Data
    # We need enough data to fill the buffers (200+ candles for Trend)
    for i in range(250):
        # Create a trend: Price Rises
        price = base_price + (i * 50)

        # Add volatility
        if 50 < i < 70: price -= 2000 # Dip
        if 150 < i < 170: price += 2000 # Spike

        event = KlineEvent(
            symbol="BTCUSDT",
            interval="1",
            open=price, close=price, high=price+10, low=price-10, volume=1000,
            timestamp=int(time.time() * 1000) + (i * 60000)
        )
        await event_bus.publish(event)

        # Sleep to let loop process
        await asyncio.sleep(0.001)

    # Wait for processing
    await asyncio.sleep(2)

    print("--- Verification Results ---")

    # Check Database for Signals
    from antigravity.database import Database, DBSignal
    db = Database()
    session = db.Session()
    try:
        signals = session.query(DBSignal).order_by(DBSignal.created_at.desc()).limit(20).all()

        if signals:
            print(f"SUCCESS: Found {len(signals)} recent signals in DB.")
            for s in signals:
                print(f" - {s.strategy} | {s.symbol} | {s.type} | {s.reason}")
        else:
            print("WARNING: No signals found in DB.")
    except Exception as e:
        print(f"DB Query Failed: {e}")
    finally:
        session.close()

    await strategy_engine.stop()
    await event_bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
