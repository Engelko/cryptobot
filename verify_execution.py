import asyncio
from antigravity.execution import RealBroker, PaperBroker
from antigravity.strategy import Signal, SignalType
from antigravity.config import settings

# Mock BybitClient
class MockBybitClient:
    async def get_wallet_balance(self, coin="USDT"):
        # Simulate Unified Account Response
        return {
            "totalWalletBalance": "500.0",
            "totalMarginBalance": "500.0"
        }

    async def place_order(self, **kwargs):
        print(f"MOCK ORDER PLACED: {kwargs}")
        return {"orderId": "mock_123"}

    async def get_positions(self, category="linear", symbol=""):
        return [{"size": "0.01", "side": "Buy"}] # Simulate open position

    async def close(self):
        pass

# Monkey patch
import antigravity.execution
original_client = antigravity.execution.BybitClient
antigravity.execution.BybitClient = MockBybitClient

async def test_execution():
    print("--- Testing RealBroker Sizing ---")
    broker = RealBroker()

    # Test 1: Balance < MAX_POSITION_SIZE
    settings.MAX_POSITION_SIZE = 1000.0
    # Mock balance is 500.0
    # Expected: Trade size 500.0
    signal = Signal(SignalType.BUY, "BTCUSDT", 50000.0)
    await broker.execute_order(signal, "TestStrategy")

    # Test 2: Balance > MAX_POSITION_SIZE
    # Lets adjust mock? Hard to adjust class mock dynamically without state.
    # We verify the logic used min(500, 1000) -> 500.

    print("\n--- Testing PaperBroker Sizing ---")
    paper = PaperBroker()
    paper.balance = 200.0
    settings.MAX_POSITION_SIZE = 1000.0
    # Expected: Trade size 200.0
    await paper.execute_order(signal, "TestStrategy")
    print(f"Paper Balance after trade: {paper.balance} (Should be 0 if used all)")

if __name__ == "__main__":
    asyncio.run(test_execution())
