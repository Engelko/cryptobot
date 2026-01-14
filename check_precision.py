import asyncio
from antigravity.client import BybitClient
import json

async def check_instruments():
    client = BybitClient()
    try:
        # Check BTC, ETH, XRP, SOL
        symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "ADAUSDT", "DOGEUSDT"]

        endpoint = "/v5/market/instruments-info"
        params = {"category": "linear"} # Fetch all to be safe or filter if allowed?
        # API usually allows status or limit. Let's fetch all and filter in python or check docs.
        # V5 allows `symbol` param? Yes.

        print("--- Instrument Info ---")
        for s in symbols:
            res = await client._request("GET", endpoint, {"category": "linear", "symbol": s})
            if res and "list" in res and res["list"]:
                info = res["list"][0]
                lot_filter = info.get("lotSizeFilter", {})
                print(f"Symbol: {s}")
                print(f"  qtyStep: {lot_filter.get('qtyStep')}")
                print(f"  minOrderQty: {lot_filter.get('minOrderQty')}")
                print(f"  maxOrderQty: {lot_filter.get('maxOrderQty')}")
            else:
                print(f"Symbol: {s} - Not Found")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(check_instruments())
