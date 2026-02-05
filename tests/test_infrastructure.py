import unittest
from unittest.mock import MagicMock
from antigravity.regime_detector import MarketRegimeDetector, MarketRegime, MarketRegimeData
from antigravity.router import StrategyRouter
from antigravity.strategy import Signal, SignalType

class TestInfrastructure(unittest.TestCase):
    def setUp(self):
        self.detector = MarketRegimeDetector()
        self.router = StrategyRouter()

    def test_regime_detection_trend(self):
        # Simulate Trending Data (Higher Highs, Higher Lows)
        klines = []
        price = 100
        # Create a strong uptrend
        for i in range(100):
            price += 1 # Steady uptrend
            klines.append({
                "open": price, "high": price+2, "low": price-1, "close": price+1, "volume": 1000
            })

        regime_data = self.detector.analyze("BTCUSDT", klines)

        # Given the steady uptrend, ADX should be high and EMA Short > EMA Long
        # We expect TRENDING_UP
        self.assertEqual(regime_data.regime, MarketRegime.TRENDING_UP)
        self.assertTrue(regime_data.adx > 25, f"ADX should be > 25, got {regime_data.adx}")

    def test_router_logic(self):
        # 1. Grid in Trend -> Blocked
        regime_trend = MarketRegimeData("BTC", MarketRegime.TRENDING_UP, 40, 1.0, 40, 0)
        signal = Signal(SignalType.BUY, "BTC", 100)

        allowed, reason = self.router.check_signal(signal, "GridMasterImproved", regime_trend)
        self.assertFalse(allowed, "Grid should be blocked in Trend")

        # 2. Grid in Range -> Allowed
        regime_range = MarketRegimeData("BTC", MarketRegime.RANGING, 10, 1.0, 10, 0)
        allowed, reason = self.router.check_signal(signal, "GridMasterImproved", regime_range)
        self.assertTrue(allowed, "Grid should be allowed in Range")

        # 3. Trend in Trend -> Allowed
        allowed, reason = self.router.check_signal(signal, "TrendFollowing", regime_trend)
        self.assertTrue(allowed, "Trend strategy should be allowed in Trend")

        # 4. Counter Trend -> Blocked
        signal_sell = Signal(SignalType.SELL, "BTC", 100)
        allowed, reason = self.router.check_signal(signal_sell, "TrendFollowing", regime_trend)
        self.assertFalse(allowed, "Counter-trend signal should be blocked")

if __name__ == "__main__":
    unittest.main()
