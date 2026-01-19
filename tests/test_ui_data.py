import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, text
from antigravity.database import db
from antigravity.config import settings

class TestUIData(unittest.TestCase):
    def setUp(self):
        # Use in-memory DB for speed/safety
        self.engine = create_engine('sqlite:///:memory:')
        db.engine = self.engine
        db.Session = MagicMock()

    def test_market_regime_query(self):
        """Verify the SQL query used by Dashboard for Market Regime works."""
        # Setup table
        with self.engine.connect() as conn:
            conn.execute(text("CREATE TABLE market_regime (id INTEGER PRIMARY KEY, symbol TEXT, regime TEXT, adx FLOAT, volatility FLOAT, updated_at TIMESTAMP)"))
            conn.execute(text("INSERT INTO market_regime (symbol, regime, adx, volatility) VALUES ('BTCUSDT', 'TRENDING_UP', 45.0, 1.2)"))
            conn.commit()

        # Test Query
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM market_regime ORDER BY updated_at DESC")).fetchall()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], 'BTCUSDT')
        self.assertEqual(result[0][2], 'TRENDING_UP')

    def test_signals_query(self):
        """Verify Signals query with rejection reason."""
        with self.engine.connect() as conn:
            conn.execute(text("CREATE TABLE signals (id INTEGER PRIMARY KEY, strategy TEXT, symbol TEXT, type TEXT, price FLOAT, reason TEXT, created_at TIMESTAMP)"))
            conn.execute(text("INSERT INTO signals (strategy, symbol, type, price, reason) VALUES ('Grid', 'ETHUSDT', 'BUY', 2000, '[REJECTED: Market Regime] Blocked by Router')"))
            conn.commit()

        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM signals WHERE reason LIKE '%REJECTED%'")).fetchall()

        self.assertTrue(len(result) > 0)
        self.assertIn("REJECTED", result[0][5])

if __name__ == '__main__':
    unittest.main()
