import asyncio
import os
from antigravity.config import settings
from antigravity.execution import execution_manager
from antigravity.strategy import Signal, SignalType
from antigravity.client import BybitClient
from antigravity.logging import configure_logging, get_logger

# Configure logging to see output
configure_logging()
logger = get_logger("verify_execution")

async def verify_real_execution():
    print("--- Starting Execution Verification ---")

    # 0. Check Persistence (The User's Main Concern)
    db_path = "storage/data.db"
    print(f"Checking for database at: {db_path}...")
    if os.path.exists(db_path):
        size = os.path.getsize(db_path)
        print(f"✅ SUCCESS: Database file found! Size: {size} bytes.")
        print("   This confirms data is persisting across restarts.")
    else:
        print(f"❌ FAILURE: Database file NOT found at {db_path}.")
        # Check root just in case
        if os.path.exists("data.db"):
             print(f"   WARNING: Found 'data.db' in ROOT directory. It should be in 'storage/' to persist.")

    # 1. Check Mode
    print(f"\nSimulation Mode: {settings.SIMULATION_MODE}")
    print(f"Testnet: {settings.BYBIT_TESTNET}")

    if settings.SIMULATION_MODE:
        print("WARNING: Bot is in Simulation Mode. This will only test Paper Trading.")

    # 2. Get Current Price for BTC
    client = BybitClient()
    current_price = 50000.0 # Fallback
    try:
        # Fetch 1 candle (limit=1) for 1-minute interval
        kline = await client.get_kline(symbol="BTCUSDT", interval="1", limit=1)
        print(f"\nRaw Kline Data: {kline}") # Print raw data for debugging

        if kline and len(kline) > 0:
            # Kline format: [startTime, open, high, low, close, volume, turnover]
            # We use 'close' price (index 4)
            close_price = float(kline[0][4])
            current_price = close_price
            print(f"Parsed Close Price: {current_price}")
        else:
            print("Failed to fetch price, using fallback.")
    except Exception as e:
        print(f"Error fetching price: {e}")
    finally:
        await client.close()

    # 3. Create a Test Signal
    test_signal = Signal(
        type=SignalType.BUY,
        symbol="BTCUSDT",
        price=current_price,
        reason="Manual Verification Test"
    )

    print(f"\nInjecting Signal: {test_signal}")

    # 4. Execute
    try:
        await execution_manager.execute(test_signal, "Manual_Check")
        print("Execution command sent. Check logs for 'real_buy_filled' or errors.")
    except Exception as e:
        print(f"Execution failed with exception: {e}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(verify_real_execution())
