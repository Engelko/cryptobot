import pandas as pd
import ta
from typing import Optional, List
from antigravity.strategy import BaseStrategy, Signal, SignalType
from antigravity.event import MarketDataEvent, KlineEvent
from antigravity.strategies.config import VolatilityConfig

class VolatilityBreakoutStrategy(BaseStrategy):
    def __init__(self, config: VolatilityConfig, symbols: List[str]):
        super().__init__(config.name, symbols)
        self.config = config
        self.klines = {s: [] for s in symbols}
        self.min_klines = config.atr_period + 10

    async def on_market_data(self, event: MarketDataEvent) -> Optional[Signal]:
        if isinstance(event, KlineEvent):
            if event.symbol not in self.symbols:
                return None

            self.klines[event.symbol].append({
                "timestamp": event.timestamp,
                "high": event.high,
                "low": event.low,
                "close": event.close,
            })

            if len(self.klines[event.symbol]) > self.min_klines + 100:
                self.klines[event.symbol].pop(0)

            return self._calculate_signal(event.symbol)
        return None

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        data = self.klines[symbol]
        if len(data) < self.min_klines:
            return None

        df = pd.DataFrame(data)

        # ATR
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=self.config.atr_period)

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # Simple Breakout Logic using ATR
        # If Price moves more than X * ATR from previous close

        upper_bound = prev["close"] + (prev["atr"] * self.config.multiplier)
        lower_bound = prev["close"] - (prev["atr"] * self.config.multiplier)

        if curr["close"] > upper_bound:
             return Signal(SignalType.BUY, symbol, curr["close"], reason="Volatility Breakout (Up)")

        if curr["close"] < lower_bound:
             return Signal(SignalType.SELL, symbol, curr["close"], reason="Volatility Breakout (Down)")

        return None
