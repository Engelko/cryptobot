import asyncio
from antigravity.client import BybitClient
from antigravity.config import settings
from antigravity.exceptions import APIError

async def verify_api():
    print("--- Bybit API Connectivity Check ---")
    print(f"Target: {'Testnet' if settings.BYBIT_TESTNET else 'Mainnet'}")

    if not settings.BYBIT_API_KEY or not settings.BYBIT_API_SECRET:
        print("✗ API Keys not found in settings/.env")
        return

    client = BybitClient()
    try:
        # 1. Check Server Time
        server_time = await client.get_server_time()
        print(f"✓ Server Time: {server_time}")

        # 2. Check Wallet Balance
        balance = await client.get_wallet_balance()
        if balance:
            print(f"✓ API Keys valid")
            total_equity = balance.get("totalEquity", "N/A")
            print(f"✓ Balance (USDT): {total_equity}")
        else:
            print("✗ Could not fetch balance (check API key permissions)")

        # 3. Check Positions
        positions = await client.get_positions(category="linear")
        print(f"✓ Active Positions: {len(positions)}")

    except APIError as e:
        print(f"✗ API Error: {e.code} - {e.message}")
        if e.code == 10003:
            print("  Hint: Invalid API key")
        elif e.code == 10004:
            print("  Hint: Signature error (check API secret or system time)")
    except Exception as e:
        print(f"✗ Connection error: {str(e)}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(verify_api())
