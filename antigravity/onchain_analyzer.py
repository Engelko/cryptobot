import aiohttp
import asyncio
import time
from typing import Dict, Any, Optional, List
from antigravity.logging import get_logger
from antigravity.config import settings
from antigravity.telegram_alerts import telegram_alerts

logger = get_logger("onchain_analyzer")

SYMBOL_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "XRPUSDT": "ripple",
    "ADAUSDT": "cardano",
    "DOGEUSDT": "dogecoin",
    "DOTUSDT": "polkadot",
    "MATICUSDT": "polygon",
    "LINKUSDT": "chainlink",
    "AVAXUSDT": "avalanche-2",
}

class OnchainAnalyzer:
    def __init__(self):
        # API Keys from settings
        self.coingecko_api_key = getattr(settings, "COINGECKO_API_KEY", "")
        self.messari_api_key = getattr(settings, "MESSARI_API_KEY", "")

        # Cache management
        self._score_cache = {"value": 0.5, "timestamp": 0}
        self._whale_cache = {"safe": True, "timestamp": 0}
        self.last_whale_activity = 0

        # Configurable TTLs (Optimized for Rate Limits)
        self.score_cache_ttl = 1800  # 30 minutes
        self.whale_cache_ttl = 600   # 10 minutes

        # Rate limiting state
        self.backoff_multiplier = 1.0

    async def fetch_onchain_data(self) -> None:
        """
        Fetch market sentiment from Messari (Exchange Flows) + Alternative.me (Fear & Greed).
        Replaces Glassnode logic.
        """
        # 1. Check Cache
        if time.time() - self._score_cache['timestamp'] < (self.score_cache_ttl * self.backoff_multiplier):
            logger.debug("onchain_score_cached", score=self._score_cache['value'])
            return

        if not self.messari_api_key:
            logger.warning("messari_key_missing", message="Using default neutral score")
            self._score_cache = {"value": 0.5, "timestamp": time.time()}
            return

        try:
            async with aiohttp.ClientSession() as session:
                # Parallel fetch
                results = await asyncio.gather(
                    self._get_messari_netflow(session),
                    self._get_fear_greed_index(session),
                    return_exceptions=True
                )

                netflow = results[0] if not isinstance(results[0], Exception) else 0.0
                fear_greed = results[1] if not isinstance(results[1], Exception) else 50

                if isinstance(results[0], Exception) or isinstance(results[1], Exception):
                    logger.error("onchain_fetch_partial_error", netflow_err=str(results[0]), fng_err=str(results[1]))

                # 3. Compute sentiment score
                score = self._compute_sentiment_score(netflow, fear_greed)

                self._score_cache = {"value": score, "timestamp": time.time()}
                self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.9) # Gradual recovery
                logger.info("onchain_score_updated", score=score, netflow=netflow, fear_greed=fear_greed)

        except Exception as e:
            logger.error("onchain_fetch_error", error=str(e))
            await telegram_alerts.send_message(f"⚠️ <b>OnchainAnalyzer Error:</b> {str(e)}")

    async def check_whale_activity(self) -> None:
        """
        Detect whale activity via volume spikes using CoinGecko.
        Replaces Whale Alert logic.
        """
        # 1. Check Cache
        if time.time() - self._whale_cache['timestamp'] < (self.whale_cache_ttl * self.backoff_multiplier):
            logger.debug("whale_check_cached", safe=self._whale_cache['safe'])
            return

        if not self.coingecko_api_key:
            self._whale_cache = {"safe": True, "timestamp": time.time()}
            return

        try:
            # Get symbols to check
            symbols_to_check = settings.TRADING_SYMBOLS
            if isinstance(symbols_to_check, str):
                symbols_to_check = [symbols_to_check]

            # Map Bybit symbols to CoinGecko IDs
            cg_ids = []
            for s in symbols_to_check:
                cg_id = SYMBOL_MAP.get(s)
                if not cg_id:
                    # Fallback mapping
                    clean_s = s.replace("USDT", "").replace("1000", "").lower()
                    cg_id = clean_s
                cg_ids.append(cg_id)

            # Since market_chart doesn't support batching in a single call for historical volumes,
            # but we want to be efficient.
            # CoinGecko Demo tier has 30 calls/min.
            # If we have many symbols, we should be careful.

            spike_detected = False
            async with aiohttp.ClientSession() as session:
                # We do them sequentially or in small batches to respect rate limits if many symbols
                # For now, let's do them in a gather but limit concurrency if needed.
                for cg_id in cg_ids:
                    if await self._detect_volume_spike(session, cg_id):
                        spike_detected = True
                        break # One spike is enough to trigger whale safety protocol

            if spike_detected:
                self.last_whale_activity = time.time()
                self._whale_cache = {"safe": False, "timestamp": time.time()}
                logger.warning("whale_activity_detected", source="volume_spike")
            else:
                self._whale_cache = {"safe": True, "timestamp": time.time()}

            self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.9)

        except Exception as e:
            logger.error("whale_check_error", error=str(e))
            # Fallback to safe but alert
            self._whale_cache = {"safe": True, "timestamp": time.time()}
            if "429" in str(e):
                self.backoff_multiplier *= 2
                await telegram_alerts.send_message("⚠️ <b>CoinGecko Rate Limit Hit!</b> Increasing backoff.")

    def get_score(self) -> float:
        """Returns bullish/bearish score (0.0 - 1.0)."""
        return self._score_cache['value']

    def is_whale_safe(self) -> bool:
        """Returns False if recent whale activity detected (last 30 mins)."""
        if time.time() - self.last_whale_activity < 1800: # 30 min
            return False
        return self._whale_cache['safe']

    # ============================================================================
    # PRIVATE METHODS
    # ============================================================================

    async def _get_messari_netflow(self, session: aiohttp.ClientSession) -> float:
        url = "https://data.messari.io/api/v1/assets/bitcoin/metrics/exchange-flows/statistics"
        headers = {"x-messari-api-key": self.messari_api_key}

        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status == 429:
                self.backoff_multiplier *= 1.5
                raise Exception("Messari Rate Limit (429)")
            if resp.status != 200:
                logger.warning("messari_netflow_error", status=resp.status)
                return 0.0

            data = await resp.json()
            return data.get('data', {}).get('net_flow', 0.0)

    async def _get_fear_greed_index(self, session: aiohttp.ClientSession) -> int:
        url = "https://api.alternative.me/fng/?limit=1"
        async with session.get(url, timeout=15) as resp:
            if resp.status != 200:
                logger.warning("fear_greed_error", status=resp.status)
                return 50

            data = await resp.json()
            try:
                return int(data['data'][0]['value'])
            except (IndexError, KeyError, ValueError):
                return 50

    def _compute_sentiment_score(self, netflow: float, fear_greed: int) -> float:
        """
        Logic:
        - netflow < 0 and fear_greed < 40 -> 0.8 (Bullish: Outflow + Fear)
        - netflow > 0 and fear_greed > 70 -> 0.2 (Bearish: Inflow + Greed)
        """
        # Normalize netflow to -1 to +1 (typical range -5000 to 5000 BTC/day)
        netflow_normalized = max(-1.0, min(1.0, netflow / 5000.0))
        fear_greed_normalized = fear_greed / 100.0

        if netflow_normalized < -0.2 and fear_greed < 40:
            return 0.8

        if netflow_normalized > 0.2 and fear_greed > 70:
            return 0.2

        # Linear interpolation for neutral zone
        score = 0.5
        score += 0.2 * (-netflow_normalized)
        score += 0.2 * (0.5 - fear_greed_normalized)

        return max(0.0, min(1.0, score))

    async def _detect_volume_spike(self, session: aiohttp.ClientSession, coin_id: str) -> bool:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {
            "vs_currency": "usd",
            "days": "1",
            "interval": "hourly"
        }
        headers = {"x-cg-demo-api-key": self.coingecko_api_key}

        async with session.get(url, headers=headers, params=params, timeout=15) as resp:
            if resp.status == 429:
                raise Exception(f"CoinGecko Rate Limit (429) for {coin_id}")
            if resp.status != 200:
                logger.warning("coingecko_volume_error", status=resp.status, coin=coin_id)
                return False

            data = await resp.json()
            volumes = data.get('total_volumes', [])
            if len(volumes) < 7:
                return False

            # Use last 6 hours to calculate average, compare with the most recent one
            recent_volumes = [v[1] for v in volumes[-7:]]
            avg_volume = sum(recent_volumes[:-1]) / len(recent_volumes[:-1])
            latest_volume = recent_volumes[-1]

            if avg_volume > 0 and latest_volume > avg_volume * 2.0:
                logger.warning("volume_spike_detected", coin=coin_id, latest=latest_volume, avg=avg_volume)
                return True

            return False

# Singleton
onchain_analyzer = OnchainAnalyzer()
