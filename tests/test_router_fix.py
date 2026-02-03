import asyncio
import unittest
from antigravity.strategy import Signal, SignalType
from antigravity.regime_detector import MarketRegime, MarketRegimeData
from antigravity.router import strategy_router

class TestRouter(unittest.TestCase):
    def test_trend_allowed_in_volatile(self):
        regime_data = MarketRegimeData(
            symbol="BTCUSDT",
            regime=MarketRegime.VOLATILE,
            adx=50.0,
            volatility=100.0,
            trend_strength=50.0,
            last_updated=0
        )

        signal = Signal(
            symbol="BTCUSDT",
            type=SignalType.BUY,
            price=50000.0,
            category="linear"
        )

        # GoldenCross should be allowed in VOLATILE now
        allowed = strategy_router.check_signal(signal, "GoldenCross", regime_data)
        self.assertTrue(allowed, "GoldenCross should be allowed in VOLATILE regime")
        print("\n✓ Router allowed GoldenCross in VOLATILE regime")

    def test_futures_pass_volatile(self):
        regime_data = MarketRegimeData(
            symbol="BTCUSDT",
            regime=MarketRegime.VOLATILE,
            adx=50.0,
            volatility=100.0,
            trend_strength=50.0,
            last_updated=0
        )

        signal = Signal(
            symbol="BTCUSDT",
            type=SignalType.BUY,
            price=50000.0,
            category="linear"
        )

        # General Linear check (now removed)
        allowed = strategy_router.check_signal(signal, "AnyStrategy", regime_data)
        self.assertTrue(allowed, "Futures should not be globally blocked in VOLATILE anymore")
        print("✓ Router no longer globally blocks futures in VOLATILE")

if __name__ == "__main__":
    unittest.main()
