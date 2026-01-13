import unittest
from datetime import datetime
from antigravity.strategies.grid_improved import GridMasterImproved
from antigravity.strategies.mean_reversion_improved import BollingerRSIImproved
from antigravity.strategies.trend_improved import GoldenCrossImproved

class TestGridMasterImproved(unittest.TestCase):
    def test_dynamic_range(self):
        grid = GridMasterImproved(symbol="BTCUSDT")
        grid.set_dynamic_range(current_price=91400, atr_value=1200, sigma=2.0)
        self.assertEqual(grid.lower_price, 91400 - 2400)
        self.assertEqual(grid.upper_price, 91400 + 2400)

    def test_grid_calculation(self):
        grid = GridMasterImproved(symbol="BTCUSDT", grid_levels=10)
        grid.lower_price = 40000
        grid.upper_price = 50000
        prices = grid.calculate_grid_prices()
        self.assertEqual(len(prices), 11) # 0 to 10
        self.assertEqual(prices[0], 40000)
        self.assertEqual(prices[-1], 50000)
        self.assertAlmostEqual(prices[1], 41000)

    def test_validation(self):
        with self.assertRaises(ValueError):
            GridMasterImproved(symbol="INVALID_PAIR")

class TestBollingerRSIImproved(unittest.TestCase):
    def setUp(self):
        self.strategy = BollingerRSIImproved(symbols=["BTCUSDT"], cooldown_seconds=300)

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
        """Проверка фильтра ADX"""
        current_time = datetime.now().timestamp()

        # ADX < 25 (no trend) — не пройдёт (Assuming logic: High ADX required)
        # Note: In my implementation, I followed the prompt's `if adx < threshold: return None`.
        signal = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=20,
            current_time=current_time, adx_value=15.0
        )
        self.assertIsNone(signal)

        # ADX > 25 (trend) — пройдёт
        signal = self.strategy.generate_signal(
            symbol="BTCUSDT", bb_signal="OVERSOLD", rsi_value=20,
            current_time=current_time, adx_value=35.0
        )
        self.assertIsNotNone(signal)

class TestGoldenCrossImproved(unittest.TestCase):
    def setUp(self):
        self.strategy = GoldenCrossImproved(symbols=["BTCUSDT"])

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
