import asyncio
from antigravity.strategies.grid import GridStrategy
from antigravity.strategies.config import GridConfig
from antigravity.event import KlineEvent, OrderUpdateEvent, MarketDataEvent
from antigravity.strategy import SignalType

async def test_grid_logic():
    print("Testing Grid Logic...")

    # Config: Range 100-200, 10 levels (Step 10)
    # Levels: 100, 110, 120, ..., 200
    cfg = GridConfig(
        enabled=True,
        name="TestGrid",
        lower_price=100.0,
        upper_price=200.0,
        grid_levels=10,
        amount_per_grid=1.0
    )

    strategy = GridStrategy(cfg, ["BTC"])
    await strategy.start()

    # 1. Initialize (Price = 155)
    # Levels < 155: 100, 110, 120, 130, 140, 150 (BUY)
    # Levels > 155: 160, 170, 180, 190, 200 (SELL)
    print("Sending Kline (155)...")
    evt = KlineEvent(symbol="BTC", close=155.0)
    sig = await strategy.on_market_data(evt) # Triggers init

    # Init saves pending placements. Next tick should produce signal.
    sig = await strategy.on_market_data(evt)

    if sig:
        print(f"Signal 1: {sig.type} @ {sig.price}")
    else:
        print("No Signal 1")

    # 2. Simulate Order Placement Tracking
    # Suppose Signal 1 was BUY @ 100. Order ID "ord_100".
    print("Sending Order New (100)...")
    await strategy.on_order_update(OrderUpdateEvent(
        symbol="BTC", order_id="ord_100", order_status="New", price=100.0
    ))

    state = strategy.state["BTC"]
    if "ord_100" in state["active_orders"]:
        print("SUCCESS: Order ord_100 tracked.")
    else:
        print("FAILURE: Order ord_100 not tracked.")

    # 3. Simulate Fill -> Flip
    # Order Filled. Should trigger pending counter order (Sell @ 110).
    print("Sending Order Filled (100)...")
    await strategy.on_order_update(OrderUpdateEvent(
        symbol="BTC", order_id="ord_100", order_status="Filled", side="Buy", price=100.0
    ))

    if "ord_100" not in state["active_orders"]:
        print("SUCCESS: Order ord_100 removed.")

    if state.get("pending_counter_orders"):
        pending = state["pending_counter_orders"][0]
        print(f"Pending Counter: {pending['side']} @ {pending['price']}")
        # Side is stored as string "SELL" now
        if pending['price'] == 110.0 and pending['side'] == "SELL":
             print("SUCCESS: Counter order logic correct.")
        else:
             print("FAILURE: Counter order logic incorrect.")
    else:
        print("FAILURE: No counter order generated.")

    await strategy.stop()

if __name__ == "__main__":
    asyncio.run(test_grid_logic())
