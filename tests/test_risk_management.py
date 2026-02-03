import unittest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from antigravity.risk import RiskManager, TradingMode
from antigravity.strategy import Signal, SignalType
from antigravity.config import settings

class TestNewRisk(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch('antigravity.database.db.get_risk_state', return_value=None)
    def test_risk_manager_emergency_stop(self, mock_get_state):
        rm = RiskManager()
        rm.initial_deposit = 100.0

        # Mock get_equity to return 40 (below 50%)
        rm.get_equity = AsyncMock(return_value=40.0)
        rm._get_balance = AsyncMock(return_value=40.0)

        signal = Signal(symbol="BTCUSDT", type=SignalType.BUY, price=50000.0)

        # We need to mock _is_reduce_only to avoid API calls
        rm._is_reduce_only = AsyncMock(return_value=False)
        rm._close_all_positions = AsyncMock()

        allowed = self.loop.run_until_complete(rm.check_signal(signal))
        self.assertFalse(allowed)
        self.assertEqual(rm.trading_mode, TradingMode.EMERGENCY_STOP)

    @patch('antigravity.database.db.get_risk_state', return_value=None)
    def test_risk_manager_leverage_cap(self, mock_get_state):
        rm = RiskManager()
        rm.initial_deposit = 1000.0
        rm.get_equity = AsyncMock(return_value=1000.0)
        rm._get_balance = AsyncMock(return_value=1000.0)
        rm._is_reduce_only = AsyncMock(return_value=False)

        signal = Signal(symbol="BTCUSDT", type=SignalType.BUY, price=50000.0, leverage=10.0)

        allowed = self.loop.run_until_complete(rm.check_signal(signal))
        self.assertTrue(allowed)
        self.assertEqual(signal.leverage, 3.0) # Capped

    @patch('antigravity.database.db.get_risk_state', return_value=None)
    def test_risk_manager_recovery_mode(self, mock_get_state):
        rm = RiskManager()
        rm.initial_deposit = 1000.0
        # 75% equity (between 50% and 80%)
        rm.get_equity = AsyncMock(return_value=750.0)
        rm._get_balance = AsyncMock(return_value=750.0)
        rm._is_reduce_only = AsyncMock(return_value=False)

        signal = Signal(symbol="BTCUSDT", type=SignalType.BUY, price=50000.0)

        allowed = self.loop.run_until_complete(rm.check_signal(signal))
        self.assertTrue(allowed)
        self.assertEqual(rm.trading_mode, TradingMode.RECOVERY)
        self.assertEqual(signal.category, "spot")
        self.assertEqual(signal.leverage, 1.0)

if __name__ == '__main__':
    unittest.main()
