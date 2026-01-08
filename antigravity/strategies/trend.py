import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import TrendConfig
from antigravity.logging import get_logger

logger = get_logger("strategy_trend")

class TrendFollowingStrategy(BaseStrategy):
    def __init__(self, config: TrendConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        self.klines = {s: [] for s in symbols}
        self.min_klines = config.slow_period + 10

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None

            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "close": event.close,
            })

            if len(self.klines[event.symbol]) > self.min_klines + 100:
                self.klines[event.symbol].pop(0)

            # Telemetry (move to on_market_data to see early heartbeat)
            self.ticks_processed += 1
            if self.ticks_processed % 2 == 0:
                count = len(self.klines[event.symbol])
                status = f"Collecting Data {count}/{self.min_klines}" if count < self.min_klines else self.last_indicator_status
                logger.info("strategy_heartbeat", name=self.name, symbol=event.symbol, status=status)

            return self._calculate_signal(event.symbol)
        return None

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        data = self.klines[symbol]
        if len(data) < self.min_klines:
            return None

        df = pd.DataFrame(data)

        # Calculate SMAs
        df["fast_sma"] = ta.trend.sma_indicator(df["close"], window=self.config.fast_period)
        df["slow_sma"] = ta.trend.sma_indicator(df["close"], window=self.config.slow_period)

        if len(df) < 2:
            return None

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # Golden Cross (Fast crosses above Slow)
        if prev["fast_sma"] <= prev["slow_sma"] and curr["fast_sma"] > curr["slow_sma"]:
            return Signal(SignalType.BUY, symbol, curr["close"], reason="Golden Cross")

        # Death Cross (Fast crosses below Slow)
        if prev["fast_sma"] >= prev["slow_sma"] and curr["fast_sma"] < curr["slow_sma"]:
            return Signal(SignalType.SELL, symbol, curr["close"], reason="Death Cross")

        # Telemetry
        self.last_indicator_status = f"Fast={curr['fast_sma']:.2f} Slow={curr['slow_sma']:.2f}"

        return None
