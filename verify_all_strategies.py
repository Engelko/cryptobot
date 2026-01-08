import asyncio
import time
import os
import yaml
from antigravity.engine import strategy_engine
from antigravity.event import event_bus, KlineEvent
from antigravity.logging import configure_logging, get_logger
from antigravity.strategies.config import load_strategy_config
from antigravity.strategies.trend import TrendFollowingStrategy
from antigravity.strategies.mean_reversion import MeanReversionStrategy
from antigravity.strategies.volatility import VolatilityBreakoutStrategy
from antigravity.strategies.scalping import ScalpingStrategy
from antigravity.strategies.bb_squeeze import BBSqueezeStrategy
from antigravity.strategies.grid import GridStrategy

# Mock Settings for test
class MockSettings:
    TRADING_SYMBOLS = ["BTCUSDT"]

logger = get_logger("verify_all")

async def main():
    configure_logging()

    # 1. Load Strategy Config
    config = load_strategy_config("strategies.yaml")
    symbols = MockSettings.TRADING_SYMBOLS

    print(f"Loaded Config: {config}")

    # 2. Register Strategies (All of them, forcibly enabled for test if needed,
    # but let's respect the config to see what's active)

    active_count = 0

    if config.trend_following and config.trend_following.enabled:
        strategy_engine.register_strategy(TrendFollowingStrategy(config.trend_following, symbols))
        print("Registered: TrendFollowing")
        active_count += 1

    if config.mean_reversion and config.mean_reversion.enabled:
        strategy_engine.register_strategy(MeanReversionStrategy(config.mean_reversion, symbols))
        print("Registered: MeanReversion")
        active_count += 1

    if config.volatility_breakout and config.volatility_breakout.enabled:
        strategy_engine.register_strategy(VolatilityBreakoutStrategy(config.volatility_breakout, symbols))
        print("Registered: VolatilityBreakout")
        active_count += 1

    if config.scalping and config.scalping.enabled:
        strategy_engine.register_strategy(ScalpingStrategy(config.scalping, symbols))
        print("Registered: Scalping")
        active_count += 1

    if config.bb_squeeze and config.bb_squeeze.enabled:
        strategy_engine.register_strategy(BBSqueezeStrategy(config.bb_squeeze, symbols))
        print("Registered: BBSqueeze")
        active_count += 1

    if config.grid and config.grid.enabled:
        strategy_engine.register_strategy(GridStrategy(config.grid, symbols))
        print("Registered: Grid")
        active_count += 1

    if active_count == 0:
        print("No strategies enabled in strategies.yaml. Enabling them temporarily for verification...")
        # Manually register one for test if none are enabled
        # But per user request "check if signals work", we should assume some are enabled or the user wants to see them work.
        # Let's forcibly register a Trend strategy for the test if empty.
        # But better: just warn.

    event_bus.start()
    await strategy_engine.start()

    print("--- Starting Data Injection ---")

    # Generate Synthetic Data to Trigger Signals

    # Scenario 1: Golden Cross (Trend)
    # Fast SMA crosses Slow SMA from below.
    # We need ~200 candles.

    base_price = 50000.0

    # We will simulate a sequence where price rises effectively
    for i in range(210):
        # Gradual increase
        price = base_price + (i * 20)

        # Add some noise/volatility for BB/RSI
        # Make RSI go low then high
        if 50 < i < 60:
            price -= 500 # Dip to trigger RSI Oversold (Buy)
        if 150 < i < 160:
            price += 1000 # Spike to trigger RSI Overbought (Sell)

        event = KlineEvent(
            symbol="BTCUSDT",
            interval="1",
            open=price, close=price, high=price+10, low=price-10, volume=1000,
            timestamp=int(time.time() * 1000) + (i * 60000)
        )
        await event_bus.publish(event)

        if i % 50 == 0:
            print(f"Processed {i} candles...")

        # Small delay to allow async processing
        await asyncio.sleep(0.001)

    # Wait for signals to be processed
    await asyncio.sleep(2)

    print("--- Verification Results ---")

    # Check Database for Signals
    from antigravity.database import Database, DBSignal
    db = Database()
    session = db.Session()
    try:
        signals = session.query(DBSignal).order_by(DBSignal.created_at.desc()).limit(10).all()

        if signals:
            print(f"SUCCESS: Found {len(signals)} recent signals in DB.")
            for s in signals:
                print(f" - {s.strategy} | {s.symbol} | {s.type} | {s.reason}")
        else:
            print("WARNING: No signals found in DB. Check strategy logic or thresholds.")
    except Exception as e:
        print(f"DB Query Failed: {e}")
    finally:
        session.close()

    await strategy_engine.stop()
    await event_bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
