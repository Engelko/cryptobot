import asyncio
from unittest.mock import MagicMock, AsyncMock
from antigravity.execution import RealBroker
from antigravity.strategy import Signal, SignalType
from antigravity.event import event_bus, TradeClosedEvent

async def test_real_broker_pnl_estimation():
    print("--- Test RealBroker PnL Estimation & Event ---")

    # 1. Mock Client (Must be AsyncMock for await calls)
    mock_client = AsyncMock()
    mock_client.get_wallet_balance.return_value = {"totalWalletBalance": "1000.0"}

    # Mock Open Position: Size 0.1, Entry 50000
    mock_client.get_positions.return_value = [{"size": "0.1", "avgPrice": "50000"}]

    # Mock Order Response
    mock_client.place_order.return_value = {"orderId": "12345"}
    mock_client.close = AsyncMock()

    # Patch BybitClient in execution module
    import antigravity.execution
    original_client = antigravity.execution.BybitClient
    antigravity.execution.BybitClient = MagicMock(return_value=mock_client)

    # 2. Setup RealBroker
    broker = RealBroker()

    # 3. Create Sell Signal (Price 40000 -> Loss)
    # Entry 50000, Exit 40000, Qty 0.1 -> Loss = (40000 - 50000) * 0.1 = -1000
    signal = Signal(symbol="BTCUSDT", type=SignalType.SELL, price=40000.0, reason="Test Close")

    # 4. Subscribe to Event to verify emission
    received_events = []
    async def handler(event):
        if isinstance(event, TradeClosedEvent):
            received_events.append(event)
    event_bus.subscribe(TradeClosedEvent, handler)
    event_bus.start()

    try:
        # 5. Execute
        await broker.execute_order(signal, "TEST_STRATEGY")

        # Allow async processing
        await asyncio.sleep(0.1)

        # 6. Verify
        if not received_events:
            print("FAIL: No TradeClosedEvent received")
            return

        evt = received_events[0]
        print(f"Received Event: PnL={evt.pnl}, ExecType={evt.execution_type}")

        assert evt.execution_type == "REAL", "Execution type should be REAL"
        assert abs(evt.pnl - (-1000.0)) < 0.01, f"PnL should be approx -1000.0, got {evt.pnl}"

        print("PASS: RealBroker PnL Verified")

    finally:
        await event_bus.stop()
        antigravity.execution.BybitClient = original_client

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_real_broker_pnl_estimation())
