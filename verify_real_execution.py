import asyncio
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

    # 1. Check Mode
    print(f"Simulation Mode: {settings.SIMULATION_MODE}")
    print(f"Testnet: {settings.BYBIT_TESTNET}")

    if settings.SIMULATION_MODE:
        print("WARNING: Bot is in Simulation Mode. This will only test Paper Trading.")

    # 2. Get Current Price for BTC
    client = BybitClient()
    current_price = 50000.0 # Fallback
    try:
        # Use get_kline instead of get_tickers since get_tickers is not implemented
        # Fetch 1 candle (limit=1) for 1-minute interval
        kline = await client.get_kline(symbol="BTCUSDT", interval="1", limit=1)
        if kline and len(kline) > 0:
            # Kline format: [startTime, open, high, low, close, volume, turnover]
            # We use 'close' price (index 4)
            current_price = float(kline[0][4])
            print(f"Current BTC Price: {current_price}")
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

    print(f"Injecting Signal: {test_signal}")

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
