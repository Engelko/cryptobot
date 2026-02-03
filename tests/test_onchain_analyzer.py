import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from antigravity.onchain_analyzer import OnchainAnalyzer

@pytest.fixture
def analyzer():
    # Create a fresh instance for each test to avoid cache pollution
    with patch('antigravity.onchain_analyzer.settings') as mock_settings:
        mock_settings.COINGECKO_API_KEY = "test_cg"
        mock_settings.MESSARI_API_KEY = "test_messari"
        mock_settings.TRADING_SYMBOLS = ["BTCUSDT"]
        return OnchainAnalyzer()

@pytest.mark.asyncio
async def test_messari_netflow_bullish(analyzer):
    """Test: Negative netflow (outflow) should contribute to bullish score."""
    with patch.object(analyzer, '_get_messari_netflow', new_callable=AsyncMock) as mock_netflow, \
         patch.object(analyzer, '_get_fear_greed_index', new_callable=AsyncMock) as mock_fng:

        mock_netflow.return_value = -2000.0
        mock_fng.return_value = 30

        await analyzer.fetch_onchain_data()

    score = analyzer.get_score()
    # netflow -2000 (bullish) + fear 30 (bullish) should be >= 0.7
    assert score >= 0.7, f"Expected bullish score, got {score}"

@pytest.mark.asyncio
async def test_fear_greed_extreme_greed(analyzer):
    """Test: High fear & greed index should contribute to bearish score."""
    with patch.object(analyzer, '_get_messari_netflow', new_callable=AsyncMock) as mock_netflow, \
         patch.object(analyzer, '_get_fear_greed_index', new_callable=AsyncMock) as mock_fng:

        mock_netflow.return_value = 1000.0
        mock_fng.return_value = 85

        await analyzer.fetch_onchain_data()

    score = analyzer.get_score()
    # netflow 1000 (bearish) + greed 85 (bearish) should be <= 0.4
    assert score <= 0.4, f"Expected bearish score, got {score}"

@pytest.mark.asyncio
async def test_volume_spike_detection(analyzer):
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

    spike = await analyzer._detect_volume_spike(mock_session, "bitcoin")
    assert spike is True

@pytest.mark.asyncio
async def test_cache_prevents_duplicate_calls(analyzer):
    """Test: Internal cache prevents unnecessary API calls."""
    analyzer._score_cache = {"value": 0.77, "timestamp": time.time()}

    with patch.object(analyzer, '_get_messari_netflow', new_callable=AsyncMock) as mock_messari:
        await analyzer.fetch_onchain_data()
        mock_messari.assert_not_called()

@pytest.mark.asyncio
async def test_whale_safety_timer(analyzer):
    """Test: is_whale_safe returns False for 30 mins after spike."""
    analyzer.last_whale_activity = time.time() - 600 # 10 mins ago
    assert analyzer.is_whale_safe() is False

    analyzer.last_whale_activity = time.time() - 1900 # 31 mins ago
    assert analyzer.is_whale_safe() is True

@pytest.mark.asyncio
async def test_backoff_on_429(analyzer):
    """Test: 429 error increases backoff multiplier."""
    mock_session = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_session.get.return_value.__aenter__.return_value = mock_resp

    initial_backoff = analyzer.backoff_multiplier

    try:
        await analyzer._get_messari_netflow(mock_session)
    except Exception as e:
        assert "Rate Limit" in str(e)

    assert analyzer.backoff_multiplier > initial_backoff
