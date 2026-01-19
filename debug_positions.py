import asyncio
import os
from antigravity.client import BybitClient
from antigravity.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("debug_positions")

async def main():
    client = BybitClient()
    try:
        print("--- Fetching Positions (Linear) ---")
        positions = await client.get_positions(category="linear")
        print(f"Found {len(positions)} positions.")
        for p in positions:
            print(f"Symbol: {p.get('symbol')}")
            print(f"  Side: {p.get('side')}")
            print(f"  Size: {p.get('size')}")
            print(f"  Entry: {p.get('avgPrice')}")
            print(f"  Leverage: {p.get('leverage')}")
            print(f"  Raw: {p}")
            print("-" * 20)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
