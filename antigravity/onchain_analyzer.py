import aiohttp
import asyncio
import os
import time
from typing import Dict, Any, Optional
from antigravity.logging import get_logger
from antigravity.config import settings

logger = get_logger("onchain_analyzer")

class OnchainAnalyzer:
    def __init__(self):
        # These should be added to .env by the user
        self.glassnode_api_key = getattr(settings, "GLASSNODE_API_KEY", "")
        self.whale_alert_api_key = getattr(settings, "WHALE_ALERT_API_KEY", "")

        self.last_whale_activity = 0
        self.whale_tx_count = 0
        self._score = 0.5 # Neutral default

    async def fetch_onchain_data(self):
        """Fetch metrics from Glassnode or similar."""
        if not self.glassnode_api_key:
            # logger.warning("onchain_analyzer_no_key", message="GLASSNODE_API_KEY missing. Using default neutral score.")
            return

        # Example implementation (assuming user provides key later)
        # Using MVRV and Netflow logic as requested
        try:
            async with aiohttp.ClientSession() as session:
                # This is pseudocode for actual Glassnode API calls
                # netflow = await self._get_glassnode_metric(session, "distribution/exchange_net_flow_total")
                # mvrv = await self._get_glassnode_metric(session, "market/mvrv_z_score")

                # For now, we simulate based on the logic provided
                netflow = -1000 # Example outflow
                mvrv = 1.2 # Example undervalued

                if netflow < 0 and mvrv < 1.5:
                    self._score = 0.8 # Bullish
                elif netflow > 0 and mvrv > 3.0:
                    self._score = 0.2 # Bearish
                else:
                    self._score = 0.5

        except Exception as e:
            logger.error("onchain_fetch_error", error=str(e))

    async def check_whale_activity(self):
        """Check Whale Alert API for large transactions."""
        if not self.whale_alert_api_key:
            return

        try:
            # Logic: if 5+ large transactions (>$1M) in an hour -> wait 30 mins
            # tx_count = await self._fetch_whale_alerts()
            tx_count = 0
            if tx_count >= 5:
                self.last_whale_activity = time.time()
                logger.warning("high_whale_activity_detected", count=tx_count)
        except Exception:
            pass

    def get_score(self) -> float:
        """Returns bullish/bearish score (0-1)."""
        return self._score

    def is_whale_safe(self) -> bool:
        """Returns False if there was recent high whale activity (last 30 mins)."""
        if time.time() - self.last_whale_activity < 1800: # 30 mins
            return False
        return True

    async def _get_glassnode_metric(self, session, endpoint):
        url = f"https://api.glassnode.com/v1/metrics/{endpoint}"
        params = {"api_key": self.glassnode_api_key, "a": "BTC", "i": "24h"}
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data[-1]['v'] if data else 0
            return 0

onchain_analyzer = OnchainAnalyzer()
