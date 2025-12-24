import asyncio
import json
import logging
from antigravity.client import BybitClient
from antigravity.logging import configure_logging

# Configure basic logging to stderr
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnostics")

async def main():
    print("--- Starting API Full Verification ---")
    client = BybitClient()

    # 1. Wallet Balance
    print("\n1. Testing Wallet Balance (USDT)...")
    try:
        # We manually call what client.get_wallet_balance does to see raw outputs
        # Try UNIFIED
        print("   Requesting UNIFIED account...")
        res_unified = await client._request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED", "coin": "USDT"})
        print(f"   UNIFIED Response: {json.dumps(res_unified, indent=2)}")

        # Try CONTRACT
        print("   Requesting CONTRACT account...")
        res_contract = await client._request("GET", "/v5/account/wallet-balance", {"accountType": "CONTRACT", "coin": "USDT"})
        print(f"   CONTRACT Response: {json.dumps(res_contract, indent=2)}")

    except Exception as e:
        print(f"   ERROR: {e}")

    # 2. Positions
    print("\n2. Testing Positions (Linear)...")
    try:
        params = {"category": "linear", "settleCoin": "USDT"}
        print(f"   Requesting positions with params: {params}")
        res_pos = await client._request("GET", "/v5/position/list", params)
        print(f"   POSITIONS Response: {json.dumps(res_pos, indent=2)}")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 3. Open Orders
    print("\n3. Testing Open Orders (Linear)...")
    try:
        params = {"category": "linear", "settleCoin": "USDT"}
        print(f"   Requesting open orders with params: {params}")
        res_ord = await client._request("GET", "/v5/order/realtime", params)
        print(f"   ORDERS Response: {json.dumps(res_ord, indent=2)}")
    except Exception as e:
        print(f"   ERROR: {e}")

    # 4. Closed PnL
    print("\n4. Testing Closed PnL (Linear)...")
    try:
        params = {"category": "linear", "settleCoin": "USDT", "limit": 5}
        print(f"   Requesting closed pnl with params: {params}")
        res_pnl = await client._request("GET", "/v5/position/closed-pnl", params)
        print(f"   PNL Response: {json.dumps(res_pnl, indent=2)}")
    except Exception as e:
        print(f"   ERROR: {e}")

    await client.close()
    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
