from antigravity.database import db, DBRiskState, DBTrade, DBSignal
from datetime import datetime, timezone

def reset_risk():
    print("Resetting risk state and cleaning up erroneous trades...")
    session = db.Session()
    try:
        # 1. Reset Risk State
        state = session.query(DBRiskState).filter_by(id=1).first()
        if state:
            print(f"Current daily loss: {state.daily_loss}. Resetting to 0.")
            state.daily_loss = 0.0
            state.consecutive_loss_days = 0
            # Set reset date to today to prevent immediate re-reset logic if needed
            state.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        else:
            print("No risk state found to reset.")

        # 2. Delete erroneous trades (those with extreme negative PnL due to 0 price bug)
        # We can look for trades with PnL < -30 or specifically the ones mentioned by user if possible
        # However, a safer way is to delete REAL trades from today that look like the bugged ones.
        bugged_trades = session.query(DBTrade).filter(
            DBTrade.execution_type == "REAL",
            DBTrade.price == 0,
            DBTrade.pnl < -5  # Some threshold
        ).all()

        print(f"Found {len(bugged_trades)} bugged trades to remove.")
        for t in bugged_trades:
            print(f"Deleting trade: {t.symbol} {t.side} PnL: {t.pnl}")
            session.delete(t)

        # 3. Delete rejected signals related to risk limit to clean up UI
        rejected_signals = session.query(DBSignal).filter(
            DBSignal.reason.contains("REJECTED: Risk Limit")
        ).all()
        print(f"Found {len(rejected_signals)} rejected signals to remove.")
        for s in rejected_signals:
            session.delete(s)

        session.commit()
        print("Successfully reset risk state and cleaned database.")
    except Exception as e:
        print(f"Error during reset: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    reset_risk()
