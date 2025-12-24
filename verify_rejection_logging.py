import asyncio
from antigravity.engine import strategy_engine
from antigravity.strategy import Signal, SignalType
from antigravity.database import db
from antigravity.config import settings

# Mock Risk Manager to force rejection
# We can't easily mock the internal instance, so we rely on finding a way to trigger rejection
# MAX_DAILY_LOSS is checked.
# We will inject a signal.

async def main():
    print("Testing Signal Rejection Persistence...")

    # 1. Create a Signal
    signal = Signal(
        type=SignalType.BUY,
        symbol="BTCUSDT",
        price=100000.0,
        reason="Test Signal"
    )

    # 2. Force Risk Rejection by mocking or settings?
    # StrategyEngine has self.risk_manager.
    # Let's manually set current_daily_loss to exceed limit
    strategy_engine.risk_manager.current_daily_loss = settings.MAX_DAILY_LOSS + 100

    # 3. Handle Signal
    await strategy_engine._handle_signal(signal, "Test_Strategy")

    # 4. Verify in DB
    # We need to query the DB.
    # Using raw sqlite or sqlalchemy
    from sqlalchemy import create_engine
    import pandas as pd

    engine = create_engine(settings.DATABASE_URL)
    df = pd.read_sql("SELECT * FROM signals ORDER BY id DESC LIMIT 1", engine)

    if not df.empty:
        last_signal = df.iloc[0]
        print("Last Signal Found in DB:")
        print(last_signal)

        if "[REJECTED: Risk Limit]" in last_signal["reason"]:
            print("SUCCESS: Rejected signal was saved with correct reason.")
        else:
            print("FAILURE: Signal saved but reason incorrect (or it wasn't rejected).")
    else:
        print("FAILURE: No signal found in DB.")

if __name__ == "__main__":
    asyncio.run(main())
