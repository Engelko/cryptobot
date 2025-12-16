import aiohttp
import asyncio
from typing import List, Optional
from decimal import Decimal
import pandas as pd

from hummingbot.strategy.strategy_v2.controllers.controller_base import ControllerBase, ControllerConfigBase
from hummingbot.core.data_type.common import TradeType

# This component mimics a controller but primarily acts as a signal provider or "Copilot"
# In a real HB setup, this might be better as a script that injects data, but implementing as Controller allows standardized lifecycle.

class AICopilotConfig(ControllerConfigBase):
    controller_name: str = "ai_copilot"
    candles_connector: str = "bybit_perpetual" # Just to satisfy base class requirement of data provider
    candles_trading_pair: str = "BTC-USDT"
    interval: str = "1m"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    analysis_interval: int = 300 # 5 minutes

class AICopilot(ControllerBase):
    def __init__(self, config: AICopilotConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config
        self.last_analysis_time = 0
        self.current_sentiment = 0.0 # -1.0 to 1.0
        self.reasoning = "Initializing..."

    async def update_processed_data(self):
        # We override this to perform the AI call periodically
        now = self.market_data_provider.time()
        if now - self.last_analysis_time > self.config.analysis_interval:
            self.last_analysis_time = now
            await self.analyze_market()

    async def analyze_market(self):
        # Fetch recent candles to summarize for LLM
        df = self.market_data_provider.get_candles_df(
            connector_name=self.config.candles_connector,
            trading_pair=self.config.candles_trading_pair,
            interval=self.config.interval
        )
        if len(df) < 20:
            return

        summary = df.tail(20).to_json()

        prompt = f"""
        Analyze this market data (OHLCV) for {self.config.candles_trading_pair}.
        Return a sentiment score from -1.0 (Bearish) to 1.0 (Bullish) and a brief reasoning.
        Format: JSON {{ "score": float, "reasoning": string }}
        Data: {summary}
        """

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.config.llm_model,
                    "messages": [{"role": "user", "content": prompt}]
                }
                headers = {"Authorization": f"Bearer {self.config.llm_api_key}"}
                async with session.post(f"{self.config.llm_base_url}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data['choices'][0]['message']['content']
                        # Simple parsing assuming strict JSON return or extracting it
                        # For robustness, would need better parsing
                        import json
                        try:
                            result = json.loads(content)
                            self.current_sentiment = float(result.get("score", 0))
                            self.reasoning = result.get("reasoning", "No reasoning provided")
                            self.logger().info(f"AI Analysis: {self.current_sentiment} - {self.reasoning}")
                        except:
                            self.logger().warning("Failed to parse AI response")
        except Exception as e:
            self.logger().error(f"AI Copilot Error: {e}")

    def determine_executor_actions(self) -> List:
        # Copilot doesn't trade directly, it just provides state.
        # Other controllers could potentially read `self.current_sentiment` if they have access to this instance,
        # or we could broadcast an event.
        return []
