import asyncio
from typing import List, Dict
from antigravity.event import event_bus, KlineEvent, SentimentEvent
from antigravity.ai import AIClient
from antigravity.logging import get_logger

logger = get_logger("ai_copilot")

class AICopilot:
    def __init__(self):
        self.client = AIClient()
        self.recent_history: Dict[str, List[float]] = {} # Symbol -> Close Prices
        self.max_history = 10
        self._running = False

    async def start(self):
        self._running = True
        event_bus.subscribe(KlineEvent, self._handle_kline)
        logger.info("ai_copilot_started")

    async def stop(self):
        self._running = False
        logger.info("ai_copilot_stopped")

    async def _handle_kline(self, event: KlineEvent):
        # Accumulate history
        if event.symbol not in self.recent_history:
            self.recent_history[event.symbol] = []
        
        self.recent_history[event.symbol].append(event.close)
        
        if len(self.recent_history[event.symbol]) > self.max_history:
            self.recent_history[event.symbol].pop(0)

        # Trigger analysis every N candles (e.g., every 5 candles)
        # For demo purposes, triggering every 5th update if we have enough data
        if len(self.recent_history[event.symbol]) >= 5 and len(self.recent_history[event.symbol]) % 5 == 0:
            await self._run_analysis(event.symbol)

    async def _run_analysis(self, symbol: str):
        prices = self.recent_history[symbol]
        
        # Simple prompt construction
        start_price = prices[0]
        end_price = prices[-1]
        change_pct = ((end_price - start_price) / start_price) * 100
        
        summary = f"""
        Symbol: {symbol}
        Recent Close Prices (Last {len(prices)} candles): {prices}
        Price Change: {change_pct:.2f}%
        Trend: {"Up" if change_pct > 0 else "Down"}
        """
        
        logger.info("ai_analysis_request", symbol=symbol)
        
        result = await self.client.analyze_market(summary)
        
        # Publish Sentiment
        await event_bus.publish(SentimentEvent(
            score=result.get("score", 0.0),
            reasoning=result.get("reasoning", "No valid response"),
            model=self.client.model
        ))
        
        logger.info("ai_sentiment_published", score=result.get("score"), symbol=symbol)
