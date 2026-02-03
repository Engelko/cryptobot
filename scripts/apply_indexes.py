from sqlalchemy import text
from antigravity.database import db

def apply_indexes():
    print("Applying database indexes for performance...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_klines_symbol_ts ON klines(symbol, ts);",
        "CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_market_regime_hist ON market_regime_history(symbol, created_at);"
    ]

    with db.engine.connect() as conn:
        for idx in indexes:
            try:
                conn.execute(text(idx))
                conn.commit()
                print(f"✓ {idx.split('ON')[0].strip()}")
            except Exception as e:
                print(f"✗ Error applying index: {e}")

if __name__ == "__main__":
    apply_indexes()
