import unittest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from antigravity.onchain_analyzer import OnchainAnalyzer

class TestOnchainAnalyzer(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a fresh instance for each test to avoid cache pollution
        self.patcher = patch('antigravity.onchain_analyzer.settings')
        self.mock_settings = self.patcher.start()
        self.mock_settings.COINGECKO_API_KEY = "test_cg"
        self.mock_settings.MESSARI_API_KEY = "test_messari"
        self.mock_settings.TRADING_SYMBOLS = ["BTCUSDT"]
        self.analyzer = OnchainAnalyzer()

    def tearDown(self):
        self.patcher.stop()

    async def test_messari_netflow_bullish(self):
        """Test: Negative netflow (outflow) should contribute to bullish score."""
        with patch.object(self.analyzer, '_get_messari_netflow', new_callable=AsyncMock) as mock_netflow, \
             patch.object(self.analyzer, '_get_fear_greed_index', new_callable=AsyncMock) as mock_fng:

            mock_netflow.return_value = -2000.0
            mock_fng.return_value = 30

            await self.analyzer.fetch_onchain_data()

        score = self.analyzer.get_score()
        # netflow -2000 (bullish) + fear 30 (bullish) should be >= 0.7
        self.assertGreaterEqual(score, 0.7, f"Expected bullish score, got {score}")

    async def test_fear_greed_extreme_greed(self):
        """Test: High fear & greed index should contribute to bearish score."""
        with patch.object(self.analyzer, '_get_messari_netflow', new_callable=AsyncMock) as mock_netflow, \
             patch.object(self.analyzer, '_get_fear_greed_index', new_callable=AsyncMock) as mock_fng:

            mock_netflow.return_value = 1000.0
            mock_fng.return_value = 85

            await self.analyzer.fetch_onchain_data()

        score = self.analyzer.get_score()
        # netflow 1000 (bearish) + greed 85 (bearish) should be <= 0.4
        self.assertLessEqual(score, 0.4, f"Expected bearish score, got {score}")

    async def test_volume_spike_detection(self):
        """Test: 2x volume spike detection."""
        mock_session = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json.return_value = {
            "total_volumes": [
                [0, 100], [0, 100], [0, 100], [0, 100], [0, 100], [0, 100],
                [0, 250] # Spike
            ]
        }
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        spike = await self.analyzer._detect_volume_spike(mock_session, "bitcoin")
        self.assertTrue(spike)

    async def test_cache_prevents_duplicate_calls(self):
        """Test: Internal cache prevents unnecessary API calls."""
        self.analyzer._score_cache = {"value": 0.77, "timestamp": time.time()}

        with patch.object(self.analyzer, '_get_messari_netflow', new_callable=AsyncMock) as mock_messari:
            await self.analyzer.fetch_onchain_data()
            mock_messari.assert_not_called()

    async def test_whale_safety_timer(self):
        """Test: is_whale_safe returns False for 30 mins after spike."""
        self.analyzer.last_whale_activity = time.time() - 600 # 10 mins ago
        self.assertFalse(self.analyzer.is_whale_safe())

        self.analyzer.last_whale_activity = time.time() - 1900 # 31 mins ago
        self.assertTrue(self.analyzer.is_whale_safe())

    async def test_backoff_on_429(self):
        """Test: 429 error increases backoff multiplier."""
        mock_session = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_session.get.return_value.__aenter__.return_value = mock_resp

        initial_backoff = self.analyzer.backoff_multiplier

        try:
            await self.analyzer._get_messari_netflow(mock_session)
        except Exception as e:
            self.assertIn("Rate Limit", str(e))

        self.assertGreater(self.analyzer.backoff_multiplier, initial_backoff)

if __name__ == "__main__":
    unittest.main()
