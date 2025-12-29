import asyncio
import os
from antigravity.database import db
from antigravity.risk import RiskManager
from antigravity.event import event_bus, TradeClosedEvent
from datetime import datetime, timezone, timedelta

# Override DB URL for test if needed, but we use the one configured
# os.environ["DATABASE_URL"] = "sqlite:///test_risk.db"

async def test_reset_logic():
    print("--- Test 1: Persistence and Reset ---")

    # 1. Seed DB with old state
    old_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    db.update_risk_state(50.0, old_date)
    print(f"Seeded DB with loss=50.0, date={old_date}")

    # 2. Init RiskManager
    rm = RiskManager()
    print(f"RiskManager Loaded: Loss={rm.current_daily_loss}, Date={rm.last_reset_date}")

    # 3. Trigger Reset Check
    rm._check_reset()
    print(f"After Reset Check: Loss={rm.current_daily_loss}, Date={rm.last_reset_date}")

    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert rm.current_daily_loss == 0.0, "Loss should reset to 0.0"
    assert rm.last_reset_date == current_date, "Date should update to today"

    # Verify DB persistence of reset
    state = db.get_risk_state()
    assert state["daily_loss"] == 0.0, "DB should be updated to 0.0"

    print("PASS: Reset Logic Verified")

async def test_pnl_update():
    print("\n--- Test 2: PnL Update ---")
    rm = RiskManager()

    # 1. Update with negative PnL
    rm.update_metrics(-15.0)
    print(f"After -15.0 PnL: Loss={rm.current_daily_loss}")

    assert rm.current_daily_loss == 15.0, "Loss should increase by 15.0"

    # Verify DB
    state = db.get_risk_state()
    assert state["daily_loss"] == 15.0, "DB should record 15.0"

    # 2. Update with positive PnL
    rm.update_metrics(20.0)
    print(f"After +20.0 PnL: Loss={rm.current_daily_loss}")

    assert rm.current_daily_loss == 15.0, "Loss should NOT change on positive PnL"

    print("PASS: PnL Update Verified")

async def test_event_integration():
    print("\n--- Test 3: Event Integration ---")
    rm = RiskManager()
    start_loss = rm.current_daily_loss

    # Publish Event
    event = TradeClosedEvent(symbol="BTCUSDT", pnl=-10.0, strategy="TEST", execution_type="PAPER")
    await event_bus.publish(event)

    # Allow async loop to process
    await asyncio.sleep(0.1)

    print(f"Start Loss={start_loss}, End Loss={rm.current_daily_loss}")
    assert rm.current_daily_loss == start_loss + 10.0, "Event should trigger update"

    print("PASS: Event Integration Verified")

async def main():
    await test_reset_logic()
    await test_pnl_update()

    # Start event bus for test 3
    event_bus.start()
    try:
        await test_event_integration()
    finally:
        await event_bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
