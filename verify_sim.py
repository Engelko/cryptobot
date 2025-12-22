import asyncio
from antigravity.strategy import Signal, SignalType
from antigravity.execution import execution_manager
from antigravity.database import db, DBTrade
from antigravity.logging import configure_logging
from sqlalchemy.orm import sessionmaker

async def main():
    configure_logging()
    
    # 1. Start Paper Broker
    paper = execution_manager.paper_broker
    print(f"X-Initial Balance: ${paper.balance}")
    
    # 2. Simulate BUY Signal
    print(">> Executing BUY Signal (BTCUSDT @ $50,000)")
    buy_signal = Signal(SignalType.BUY, "BTCUSDT", 50000.0, reason="Sim Test Buy")
    await execution_manager.execute(buy_signal, "TestStrategy")
    
    print(f"X-Balance after BUY: ${paper.balance}")
    
    # 3. Simulate Price Move (Up 10%) and SELL
    print(">> Executing SELL Signal (BTCUSDT @ $55,000)")
    sell_signal = Signal(SignalType.SELL, "BTCUSDT", 55000.0, reason="Sim Test Sell")
    await execution_manager.execute(sell_signal, "TestStrategy")
    
    print(f"X-Balance after SELL: ${paper.balance}")
    
    # 4. Verify DB Records
    Session = sessionmaker(bind=db.engine)
    session = Session()
    trades = session.query(DBTrade).all()
    print(f"X-Trades in DB: {len(trades)}")
    for t in trades:
        print(f" [DB] {t.side} {t.quantity} @ {t.price} (PnL: {t.pnl})")
    session.close()

    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
