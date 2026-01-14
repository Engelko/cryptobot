from antigravity.config import settings
from antigravity.client import BybitClient
import asyncio
import os

async def check():
    print("--- Configuration Diagnostics ---")
    print(f"SIMULATION_MODE: {settings.SIMULATION_MODE}")
    print(f"BYBIT_TESTNET: {settings.BYBIT_TESTNET}")
    print(f"TRADING_SYMBOLS: {settings.TRADING_SYMBOLS}")

    # Check Environment Variables directly to see if .env is being read
    print(f"ENV[SIMULATION_MODE]: {os.environ.get('SIMULATION_MODE', 'Not Set')}")
    print(f"ENV[BYBIT_TESTNET]: {os.environ.get('BYBIT_TESTNET', 'Not Set')}")

    if settings.SIMULATION_MODE:
        print("\n[RESULT] The bot is currently in SIMULATION MODE (Paper Trading).")
        print("Orders are simulated internally and NOT sent to Bybit.")
        return

    print("\n--- API Connectivity Test (Real Mode) ---")
    client = BybitClient()
    try:
        balance = await client.get_wallet_balance()
        print("API Connection SUCCESS!")
        print(f"Wallet Balance Response: {balance}")
    except Exception as e:
        print(f"API Connection FAILED: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check())
