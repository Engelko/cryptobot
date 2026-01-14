import unittest
from datetime import datetime
from antigravity.strategies.grid_improved import GridMasterImproved
from antigravity.strategies.mean_reversion_improved import BollingerRSIImproved
from antigravity.strategies.trend_improved import GoldenCrossImproved
from antigravity.strategies.config import GridConfig, MeanReversionConfig, TrendConfig

class TestGridMasterImproved(unittest.TestCase):
    def setUp(self):
        self.config = GridConfig(name="GridMaster", lower_price=0.0, upper_price=0.0, grid_levels=10, amount_per_grid=0.001)

    def test_dynamic_range(self):
        grid = GridMasterImproved(self.config, symbols=["BTCUSDT"])
        grid.set_dynamic_range(symbol="BTCUSDT", current_price=91400, atr_value=1200, sigma=2.0)
        state = grid.grid_states["BTCUSDT"]
        self.assertEqual(state["lower"], 91400 - 2400)
        self.assertEqual(state["upper"], 91400 + 2400)

    def test_grid_calculation(self):
        config = GridConfig(name="GridMaster", lower_price=40000, upper_price=50000, grid_levels=10, amount_per_grid=0.001)
        grid = GridMasterImproved(config, symbols=["BTCUSDT"])
        prices = grid.calculate_grid_prices("BTCUSDT")
        self.assertEqual(len(prices), 11) # 0 to 10
        self.assertEqual(prices[0], 40000)
        self.assertEqual(prices[-1], 50000)
        self.assertAlmostEqual(prices[1], 41000)

    def test_validation(self):
        # We changed crashing to warning for symbols in constructor,
        # but amount < 0 still crashes
        config = GridConfig(name="GridMaster", amount_per_grid=-1)
        with self.assertRaises(ValueError):
            GridMasterImproved(config, symbols=["BTCUSDT"])

class TestBollingerRSIImproved(unittest.TestCase):
    def setUp(self):
        self.config = MeanReversionConfig(name="BollingerRSI", rsi_overbought=70, rsi_oversold=30)
        self.strategy = BollingerRSIImproved(self.config, symbols=["BTCUSDT"])
        # Override default cooldown for test predictability if needed,
        # or stick to defaults. The test relies on cooldown check.
        # But previous test passed cooldown_seconds to init. Now we can't.
        # We need to manually set it if we want to test specific timing, or rely on default 300.
        self.strategy.cooldown_seconds = 300

    def test_cooldown_filter(self):
        """Проверка, что cooldown работает"""
        current_time = datetime.now().timestamp()

        # Первый сигнал — пройдёт
        signal1 = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=20,
            current_time=current_time, adx_value=35.0
        )
        self.assertIsNotNone(signal1)

        # Второй сигнал за 60 сек (< 300) — не пройдёт
        signal2 = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=25,
            current_time=current_time + 60, adx_value=35.0
        )
        self.assertIsNone(signal2)

        # Третий сигнал за 400 сек (> 300) — пройдёт
        signal3 = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=22,
            current_time=current_time + 400, adx_value=35.0
        )
        self.assertIsNotNone(signal3)

    def test_adx_filter(self):
        """Проверка фильтра ADX (Removed restriction)"""
        current_time = datetime.now().timestamp()

        # ADX < 25 (no trend) — SHOULD PASS NOW (Mean Reversion likes sideways)
        signal = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=20,
            current_time=current_time, adx_value=15.0
        )
        self.assertIsNotNone(signal)

        # ADX > 25 (trend) — SHOULD PASS (No restriction for now)
        signal2 = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=20,
            current_time=current_time + 400, adx_value=35.0
        )
        self.assertIsNotNone(signal2)

class TestGoldenCrossImproved(unittest.TestCase):
    def setUp(self):
        self.config = TrendConfig(name="GoldenCross", fast_period=50, slow_period=200)
        self.strategy = GoldenCrossImproved(self.config, symbols=["BTCUSDT"])

    def test_adx_filter(self):
        # ADX < 25 -> No Signal
        res = self.strategy.generate_signal("BTCUSDT", 100, 90, 101, 10.0)
        self.assertIsNone(res)

        # ADX > 25 -> Signal
        res = self.strategy.generate_signal("BTCUSDT", 100, 90, 101, 30.0)
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "BUY")

if __name__ == "__main__":
    unittest.main()
