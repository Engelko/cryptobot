import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from antigravity.onchain_analyzer import onchain_analyzer
from antigravity.config import settings

async def main():
    print("=== Onchain Analyzer Live Test ===")

    if not settings.COINGECKO_API_KEY or not settings.MESSARI_API_KEY:
        print("❌ Error: COINGECKO_API_KEY or MESSARI_API_KEY missing in .env")
        print("Please set them before running this live test.")
        return

    # Test 1: Fetch sentiment score
    print("\n1. Fetching onchain data (Messari + Alternative.me)...")
    try:
        await onchain_analyzer.fetch_onchain_data()
        score = onchain_analyzer.get_score()
        print(f"   ✓ Sentiment Score: {score:.2f}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 2: Check whale activity
    print("\n2. Checking whale activity (CoinGecko volume)...")
    try:
        await onchain_analyzer.check_whale_activity()
        safe = onchain_analyzer.is_whale_safe()
        print(f"   ✓ Whale Safe: {safe}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")

    # Test 3: Verify caching
    print("\n3. Testing cache (should be instant)...")
    import time
    start = time.time()
    await onchain_analyzer.fetch_onchain_data()
    duration = time.time() - start
    print(f"   ✓ Cached call took {duration:.5f}s")
    if duration < 0.01:
        print("   ✓ Cache working correctly.")
    else:
        print("   ⚠️ Cache might not be working as expected.")

    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
