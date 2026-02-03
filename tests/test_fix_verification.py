import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from antigravity.strategy import Signal, SignalType
from antigravity.risk import RiskManager, TradingMode
from antigravity.regime_detector import MarketRegime, MarketRegimeData, market_regime_detector
from antigravity.strategies.spot_recovery import SpotRecoveryStrategy
from antigravity.config import settings

class TestBotFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        pass

    @patch('antigravity.risk.db')
    @patch('antigravity.risk.BybitClient')
    async def test_risk_manager_volatile_to_spot(self, mock_client_class, mock_db):
        mock_db.get_risk_state.return_value = {"daily_loss": 0.0, "last_reset_date": "2026-02-03", "consecutive_loss_days": 0}

        # Mock client instance
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.get_wallet_balance.return_value = {"totalWalletBalance": "1000.0"}
        mock_client.get_positions.return_value = []
        mock_client.close = AsyncMock()

        # Setup: Volatile regime
        market_regime_detector.regimes["BTCUSDT"] = MarketRegimeData(
            symbol="BTCUSDT",
            regime=MarketRegime.VOLATILE,
            adx=50.0,
            volatility=100.0,
            trend_strength=50.0,
            last_updated=0
        )

        risk_manager = RiskManager()

        signal = Signal(
            symbol="BTCUSDT",
            type=SignalType.BUY,
            price=50000.0,
            category="linear", # Initial
            leverage=3.0
        )

        # Test
        allowed = await risk_manager.check_signal(signal)

        self.assertTrue(allowed)
        self.assertEqual(signal.category, "spot")
        self.assertEqual(signal.leverage, 1.0)
        print("\n✓ RiskManager correctly converted linear to spot in VOLATILE regime")

    @patch('antigravity.strategies.spot_recovery.market_regime_detector')
    @patch('antigravity.strategy.db')
    async def test_spot_recovery_trigger(self, mock_db, mock_regime_detector):
        strategy = SpotRecoveryStrategy(["BTCUSDT"])
        strategy.is_active = True

        # Mock the engine's risk manager which is imported inside the method
        mock_engine = MagicMock()
        mock_engine.risk_manager.trading_mode = TradingMode.RECOVERY

        # Setup: Recovery Mode + Volatile Regime
        mock_regime_detector.regimes.get.return_value = MarketRegimeData(
            symbol="BTCUSDT",
            regime=MarketRegime.VOLATILE,
            adx=50.0,
            volatility=100.0,
            trend_strength=50.0,
            last_updated=0
        )

        from antigravity.event import KlineEvent
        event = KlineEvent(symbol="BTCUSDT", close=50000.0)

        # Patch the local import of strategy_engine inside on_market_data
        with patch('antigravity.engine.strategy_engine', mock_engine):
            # Test
            signal = await strategy.on_market_data(event)

            self.assertIsNotNone(signal)
            self.assertEqual(signal.type, SignalType.BUY)
            self.assertEqual(signal.reason, "SPOT_RECOVERY_START")
            self.assertEqual(signal.category, "spot")
            print("✓ SpotRecoveryStrategy triggered first buy in RECOVERY + VOLATILE")

if __name__ == "__main__":
    unittest.main()
